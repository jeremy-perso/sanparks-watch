#!/usr/bin/env python3
"""
SANParks waterhole watcher - preset-aware change detection on still cams.

One process watches every camera in cameras.py at once, each in its own thread,
so a single scheduled job produces a single commit and there are no push races.

Per camera and per frame it:
  1. polls the still JPEG, skipping unchanged bytes for free (ETag),
  2. decides which PTZ preset the frame belongs to (16x9 fingerprint),
  3. diffs it against that preset's own slowly-learned background,
  4. describes the largest connected blob of change and decides on its geometry,
  5. writes one CSV row either way, so retuning never needs the images back.

State (one background per preset) lives in ./state and is restored from the
GitHub Actions cache rather than committed, because a float background is
~330 KB and committing every preset every five minutes would bloat the repo by
hundreds of MB a day.

Thresholds live in cameras.py, per camera and split day/night. See README.
"""
import io, os, csv, json, time, hashlib, datetime, pathlib, threading, sys
import numpy as np, requests
from PIL import Image
from scipy import ndimage

from cameras import CAMERAS

# --- run-level knobs (env, set by the workflow)
RUNTIME = int(os.getenv("RUNTIME", 270))          # seconds of polling
POLL    = int(os.getenv("POLL", 10))              # seconds between polls
COLLECT = os.getenv("COLLECT", "top").lower()     # all | top | hits
TOP_N   = int(os.getenv("TOP_N", 1))              # frames kept per run in 'top'
                                                  # 1, not 3: the schedule now
                                                  # runs round the clock, 288
                                                  # runs a day, and a daylight
                                                  # JPEG archives at ~150 KB
                                                  # against ~55 KB at night
                                                  # (measured 31 Aug). At 1
                                                  # that is still ~290 frames
                                                  # per camera per day.
FORCE   = os.getenv("FORCE_ALL_HOURS", "") == "1" # ignore the active-hours gate
# Measured 30 Aug 2026: with curl_cffi, Nossob fetched fine while Talamati's
# very first request was refused. One 403 used to kill a camera for the whole
# run, so a transient refusal cost the entire session. Only give up after this
# many CONSECUTIVE 403s; any success resets the count.
FORBID_MAX = int(os.getenv("FORBID_MAX", 5))
ARCHIVE_MAX = 900                                 # long edge of archived frames

# --- analysis geometry (shared by every camera)
W, H    = 384, 216      # analysis resolution
SW, SH  = 16, 9         # preset-fingerprint resolution
BLK     = 4             # blob grid: BLK x BLK pixel blocks
BW, BH  = W // BLK, H // BLK
TS_BOX  = (0.0, 0.925, 0.22, 1.0)   # burnt-in clock, bottom left, masked out
PRESET_CAP  = 120        # refuse to learn more views than this
PRESET_TTL  = 7 * 86400 # forget a preset unseen for this long

# --- inherited thresholds; cameras.py overrides what differs
DEFAULTS = dict(SIG_TOL=11, PIX_THR=24, BLK_MIN=6, MIN_N=4, BLOB_MIN=3,
                BLOB_MAX=600, DOM_MIN=0.45, ASP_MAX=2.4, FILL_CMP=0.32,
                FILL_WIDE=0.62, EMA=0.25,
                # SIG_TOL decides which preset a frame BELONGS to. DIST_MAX
                # decides whether the match is close enough to JUDGE on. They
                # are deliberately different: a loose SIG_TOL keeps backgrounds
                # converged, a tight DIST_MAX stops us deciding on a frame that
                # is really a slightly different view. Measured 30-31 Aug 2026
                # over 906 frames: at Talamati the median changed-pixel count
                # rises from 183 (dist 0-3) to 26908 (dist 18-25).
                DIST_MAX=6.0,
                # Change split across this many separate blobs is diffuse
                # scenery (dawn light, wind), not an animal. Measured on the
                # same 906 frames: every confirmed animal scored nblobs <= 17
                # (the dove flock), while the four confirmed dawn false
                # positives scored 48, 52, 103 and 141.
                NB_MAX=25,
                # per-preset activity veto: blocks that change this often are
                # scenery that always moves (grass, leaves) and are ignored
                ACT_MAX=0.60, ACT_MIN_N=12, ACT_EMA=0.06)

ROOT  = pathlib.Path(__file__).parent
NTFY  = os.getenv("NTFY_TOPIC", "")
# A full desktop Chrome header set. Measured 30 Aug 2026: on its own this does
# NOT defeat the Cloudflare block. `requests` with these exact headers still
# returned 403 from both cameras. Kept because it costs nothing and curl_cffi
# sends them alongside the browser handshake that does the actual work.
HDRS  = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.sanparks.org/",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-site",
    "Connection": "keep-alive",
}
NB8   = np.ones((3, 3), dtype=int)
PLOCK = threading.Lock()

# Cloudflare fingerprints the TLS/HTTP2 handshake, not just the headers, and
# python-requests has an unmistakable non-browser signature. curl_cffi replays
# a real Chrome handshake. If it is not installed we fall back to requests and
# the run behaves exactly as before.
#
# MEASURED 30 Aug 2026, four clients from the same public repo and runner pool:
# requests + Mozilla UA -> 403, requests + full Chrome headers -> 403, wsrv.nl
# image proxy -> 403 upstream, curl_cffi impersonate=chrome -> both cameras
# fetch. It was the handshake, not the IP. Do not "simplify" this back to
# plain requests; every frame will 403.
IMPERSONATE = os.getenv("IMPERSONATE", "chrome")
try:
    from curl_cffi import requests as _cc
except ImportError:
    _cc = None


# SCHEMA HISTORY, because the logs change shape mid-file and any analysis has
# to split on it:
#   to 31 Aug 12:48 UTC   18 columns
#   from 31 Aug 12:48     23 columns, added dom2 cx cy bpk bsat
#   from  1 Sep bundle    26 columns, added blob2 bact veto30, and bpk/bsat
#                         now measured at source resolution so their values
#                         are NOT comparable across the boundary
CSV_COLS = ["utc", "last_modified", "preset", "n", "dist", "mode", "bright",
            "px", "blob", "blob2", "bw", "bh", "fill", "dom", "dom2", "cx", "cy",
            "bpk", "bsat", "bact", "nblobs", "blocks", "vetoed", "veto30",
            "hit", "bytes"]


class Forbidden403(Exception):
    """Cloudflare refused this request. Distinguished from ordinary network
    errors so a run of them can be counted before giving up on a camera."""


def log(msg):
    with PLOCK:
        print(msg, flush=True)


def build_mask():
    """True where pixels count. The burnt-in clock changes every minute and
    would otherwise be a small, solid, perfectly animal-shaped blob."""
    m = np.ones((H, W), dtype=bool)
    x0, y0, x1, y1 = TS_BOX
    m[int(y0 * H):int(y1 * H) + 1, int(x0 * W):int(x1 * W) + 1] = False
    return m


MASK = build_mask()
BMASK = MASK.reshape(BH, BLK, BW, BLK).all(axis=(1, 3))   # blocks fully visible


def is_night(hour, night):
    lo, hi = night
    return hour >= lo or hour < hi if lo > hi else lo <= hour < hi


def active_now(cam, now_utc):
    local = (now_utc.hour + cam["tz"]) % 24
    if FORCE:
        return True, local
    return any(a <= local < b for a, b in cam["active"]), local


def thresholds(cam, local_hour):
    t = dict(DEFAULTS)
    t.update(cam.get("thr", {}))
    if is_night(local_hour, cam.get("night", (18, 6))):
        t.update(cam.get("thr_night", {}))
    return t


def analyse(raw):
    """Brightness-normalised full frame plus coarse preset fingerprint.
    The mean is taken over visible pixels only, so the clock cannot drag it.

    Also returns the SOURCE-resolution greyscale array. See block_peaks: the
    384x216 analysis array is a 5x downsample of a 1920x1080 JPEG and averages
    away exactly the saturated cores `bsat` exists to find."""
    im = Image.open(io.BytesIO(raw)).convert("L")
    src = np.asarray(im, dtype=np.uint8)
    g = np.asarray(im.resize((W, H)), dtype=np.float32)
    bright = float(g[MASK].mean())
    g = g - bright
    s = np.asarray(im.resize((SW, SH)), dtype=np.float32)
    s = s - s.mean()
    return g, s, bright, src


def block_peaks(src):
    """Peak SOURCE pixel value in each analysis block, as a (BH, BW) array.

    MEASURED 1 Sep 2026, 77 Nossob night hits pulled back and inspected: 31 of
    them contain source pixels at 250 or above, including the 01:13 owl's
    eyeshine at 255. Every one of those logged `bsat` 0.00, because bsat was
    computed on the 384x216 array where a point source averages down to about
    155. On 493 Nossob night frames the old bsat was non-zero six times, so it
    could not have separated anything from anything. Measuring before the
    resize is the whole point of the column.

    Talamati's out-of-focus lens insects are big enough to survive a 5x
    downsample, which is why bsat looked alive there (158 of 467 night frames)
    and dead at Nossob. Same column, two different answers, one bug."""
    if src is None or src.ndim != 2:
        return None
    hs, ws = src.shape
    ry, rx = hs // BH, ws // BW
    if ry < 1 or rx < 1:
        return None
    return src[:BH * ry, :BW * rx].reshape(BH, ry, BW, rx).max(axis=(1, 3))


def change_blocks(g, bg, t):
    """Per-pixel change, folded into the BLK x BLK block grid."""
    d = (np.abs(g - bg) > t["PIX_THR"]) & MASK
    blocks = (d.reshape(BH, BLK, BW, BLK).sum(axis=(1, 3)) >= t["BLK_MIN"]) & BMASK
    return int(d.sum()), blocks


def blob_metrics(npix, blocks, peaks=None, act=None):
    """Largest connected region of change, described so animals separate from
    light: size, solidity, aspect, and how much of the change it accounts for."""
    lab, k = ndimage.label(blocks, structure=NB8)
    if k == 0:
        return dict(px=npix, blob=0, bw=1, bh=1, fill=0.0, dom=0.0,
                    dom2=0.0, blob2=0, cx=0.0, cy=0.0, bpk=0, bsat=0.0,
                    bact=0.0, nb=0, blocks=0)
    sizes = ndimage.sum(blocks, lab, range(1, k + 1))
    top = int(np.argmax(sizes)) + 1
    sel = (lab == top)
    ys, xs = np.nonzero(sel)
    bw, bh = int(np.ptp(xs) + 1), int(np.ptp(ys) + 1)   # numpy 2.0: no arr.ptp()
    n = int(sizes[top - 1])
    # INSTRUMENTATION ONLY, nothing decides on these yet.
    #  cx, cy  where the blob sits, as fractions of the frame. This one has
    #          already earned its keep: it identified all four dusk false
    #          positives of 31 Aug by location alone.
    #  dom2    KNOWN BROKEN, kept only so the column does not disappear
    #          mid-history. It divides by the sum of blobs of 3 blocks or more,
    #          but a Nossob floodlit insect IS 3 to 6 blocks, so the divisor
    #          collapses to the top blob alone and dom2 pins at exactly 1.00.
    #          Measured 1 Sep 2026 on 225 Nossob night frames with blob >= 3:
    #          73% of the 3-to-5-block frames score dom2 1.00. Substituting it
    #          for dom admitted 23 extra insect-sized frames and dropped 23
    #          animal-sized ones. Use blob2 instead.
    #  blob2   size of the SECOND largest blob. What dom2 was reaching for,
    #          without a ceiling and without an arbitrary 3-block floor.
    #  bpk     peak SOURCE pixel (0-255) inside the blob, and
    #  bsat    the share of the blob's blocks whose source peak touches 250.
    #          Both now measured before the 384x216 downsample; see block_peaks
    #          for why the old version could never fire at Nossob.
    #  bact    mean activity-veto score of the blob's own blocks. Measured
    #          1 Sep 2026: ACT_MAX 0.60 vetoed something in 3 of 493 Nossob
    #          night frames and in 0 of the 77 hits, while ~35 of those hits
    #          were swaying grass. Median changed blocks per night frame is 4,
    #          so no block ever approaches 0.60. bact says what the grass
    #          actually scores, so ACT_MAX can be set from data instead of
    #          guessed. THIS IS THE HIGHEST-VALUE NEW COLUMN.
    bpk, bsat = 0, 0.0
    if peaks is not None:
        bpk = int(peaks[sel].max())
        bsat = round(float(((peaks >= 250) & sel).sum()) / n, 2)
    bact = round(float(act[sel].mean()), 3) if act is not None else 0.0
    big = sizes[sizes >= 3]
    srt = np.sort(sizes)[::-1]
    return dict(px=npix, blob=n, bw=bw, bh=bh, bpk=bpk, bsat=bsat, bact=bact,
                fill=round(n / (bw * bh), 2),
                dom=round(n / float(sizes.sum()), 2),
                dom2=round(n / float(big.sum()), 2) if big.sum() else 0.0,
                blob2=int(srt[1]) if k > 1 else 0,
                cx=round(float(xs.mean()) / BW, 3),
                cy=round(float(ys.mean()) / BH, 3),
                nb=k, blocks=int(sizes.sum()))


def is_hit(m, n_frames, t):
    """Rejects the real failure modes: a frame that is not really this preset,
    change scattered across dozens of blobs, a long flat smear where the light
    shifts. A blob only counts if the frame is a good match to its background,
    the change is concentrated, and the blob is big, dominant and solid.

    m may carry `dist` (distance to the matched preset) and `nb` (how many
    blobs the change broke into). Both default to a passing value so that
    older callers and the archived selftest rows behave exactly as before."""
    if n_frames < t["MIN_N"]:                             return False
    if m.get("dist", 0.0) > t["DIST_MAX"]:                return False
    if m.get("nb", 1) > t["NB_MAX"]:                      return False
    if not (t["BLOB_MIN"] <= m["blob"] <= t["BLOB_MAX"]): return False
    if m["dom"] < t["DOM_MIN"]:                           return False
    asp = max(m["bw"] / m["bh"], m["bh"] / m["bw"])
    return m["fill"] >= (t["FILL_CMP"] if asp <= t["ASP_MAX"] else t["FILL_WIDE"])


class Watcher:
    def __init__(self, cam):
        self.cam   = cam
        self.name  = cam["name"]
        self.state = ROOT / "state"  / self.name
        self.hits  = ROOT / "hits"   / self.name
        self.frames= ROOT / "frames" / self.name
        self.logs  = ROOT / "logs"   / self.name
        self.state.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.presets, self.etag = [], None
        self.rows, self.keep = [], []
        self.nhits = self.nframes = 0
        self.forbidden = False
        self.f403 = 0

    # --- state -------------------------------------------------------------
    def load(self):
        p = self.state / "presets.json"
        if not p.exists():
            return
        meta = json.loads(p.read_text())
        self.etag = meta.get("etag")
        cutoff = time.time() - PRESET_TTL
        for m in meta["presets"]:
            f = self.state / f"bg{m['id']}.npy"
            if not f.exists() or m.get("seen", 0) < cutoff:
                continue
            m["bg"]  = np.load(f).astype(np.float32)
            a = self.state / f"act{m['id']}.npy"
            m["act"] = (np.load(a).astype(np.float32) if a.exists()
                        else np.zeros((BH, BW), dtype=np.float32))
            m["sig"] = np.array(m["sig"], dtype=np.float32)
            self.presets.append(m)

    def save(self):
        for m in self.presets:
            np.save(self.state / f"bg{m['id']}.npy", m["bg"].astype(np.float16))
            np.save(self.state / f"act{m['id']}.npy", m["act"].astype(np.float16))
        (self.state / "presets.json").write_text(json.dumps({
            "etag": self.etag,
            "presets": [{"id": m["id"], "sig": np.round(m["sig"], 2).tolist(),
                         "n": m["n"], "seen": m["seen"]} for m in self.presets]}, indent=1))

    def write_csv(self):
        if not self.rows:
            return
        day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        f = self.logs / f"{day}.csv"
        new = not f.exists()
        with f.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLS)
            if new:
                w.writeheader()
            w.writerows(self.rows)

    # --- io ----------------------------------------------------------------
    def grab(self):
        params = {"t": int(time.time() * 1000)}
        if _cc is not None:
            r = _cc.get(self.cam["url"], headers=HDRS, timeout=25,
                        params=params, impersonate=IMPERSONATE)
        else:
            r = requests.get(self.cam["url"], headers=HDRS, timeout=25,
                             params=params)
        if r.status_code == 403:
            raise Forbidden403("403 Forbidden")
        r.raise_for_status()
        return r.content, r.headers.get("ETag"), r.headers.get("Last-Modified")

    def archive(self, raw, stamp, pid, m):
        day = self.frames / stamp[:8]
        day.mkdir(parents=True, exist_ok=True)
        im = Image.open(io.BytesIO(raw))
        im.thumbnail((ARCHIVE_MAX, ARCHIVE_MAX))
        im.save(day / f"{stamp[9:]}_p{pid}_blob{m['blob']:04d}_f{m['fill']:.2f}.jpg",
                quality=76, optimize=True)

    def notify(self, msg, jpg):
        if not NTFY:
            return
        try:
            requests.post(f"https://ntfy.sh/{NTFY}", data=jpg, timeout=15,
                          headers={"Title": self.cam["label"], "Message": msg,
                                   "Filename": f"{self.name}.jpg", "Tags": "eyes"})
        except Exception as e:
            log(f"[{self.name}] ntfy failed: {e}")

    # --- main loop ---------------------------------------------------------
    def run(self, deadline):
        now = datetime.datetime.now(datetime.timezone.utc)
        on, local = active_now(self.cam, now)
        if not on:
            log(f"[{self.name}] asleep, local hour {local:02d} outside "
                f"{self.cam['active']}")
            return
        self.load()
        log(f"[{self.name}] awake, local {local:02d}h, "
            f"{'night' if is_night(local, self.cam.get('night',(18,6))) else 'day'} "
            f"thresholds, {len(self.presets)} presets restored")

        seen = {self.etag} if self.etag else set()
        while time.time() < deadline:
            try:
                raw, etag, lm = self.grab()
                self.f403 = 0
                key = etag or hashlib.md5(raw).hexdigest()
                if key in seen:
                    time.sleep(POLL); continue
                seen.add(key); self.etag = key
                self.handle(raw, lm)
            except Forbidden403:
                self.f403 += 1
                log(f"[{self.name}] 403 Forbidden "
                    f"({self.f403}/{FORBID_MAX} consecutive)")
                if self.f403 >= FORBID_MAX:
                    self.forbidden = True
                    return
                time.sleep(min(4 * self.f403, 20))
                continue
            except Exception as e:
                log(f"[{self.name}] error: {e}")
            time.sleep(POLL)

        self.save()
        self.flush_keep()
        self.write_csv()

    def handle(self, raw, lm):
        now   = datetime.datetime.now(datetime.timezone.utc)
        local = (now.hour + self.cam["tz"]) % 24
        t     = thresholds(self.cam, local)
        mode  = "night" if is_night(local, self.cam.get("night", (18, 6))) else "day"
        stamp = now.strftime("%Y%m%d_%H%M%S")
        g, sig, bright, src = analyse(raw)
        self.nframes += 1

        best, bd = None, 1e9
        for m in self.presets:
            d = float(np.abs(sig - m["sig"]).mean())
            if d < bd:
                best, bd = m, d

        if best is None or bd > t["SIG_TOL"]:
            if len(self.presets) >= PRESET_CAP:
                log(f"[{self.name}] {lm} preset cap reached, frame skipped "
                    f"(nearest {bd:.1f}) - consider raising SIG_TOL")
                return
            best = {"id": max([p["id"] for p in self.presets], default=-1) + 1,
                    "sig": sig, "bg": g.copy(), "n": 1, "seen": time.time(),
                    "act": np.zeros((BH, BW), dtype=np.float32)}
            self.presets.append(best)
            log(f"[{self.name}] {lm} new preset p{best['id']} (nearest {bd:.1f})")
            return

        best["n"] += 1
        best["seen"] = time.time()
        best["sig"] = best["sig"] * 0.7 + sig * 0.3

        npix, raw_blocks = change_blocks(g, best["bg"], t)

        # Learn which blocks are permanently restless for this view, then take
        # them out of the decision. At Talamati most of the frame is grass and
        # foliage that moves in every frame; without this the animal is never
        # the dominant blob.
        best["act"] = best["act"] * (1 - t["ACT_EMA"]) + raw_blocks * t["ACT_EMA"]
        vetoed = 0
        blocks = raw_blocks
        if best["n"] >= t["ACT_MIN_N"]:
            quiet = best["act"] < t["ACT_MAX"]
            vetoed = int((raw_blocks & ~quiet).sum())
            blocks = raw_blocks & quiet
        # What a lower ACT_MAX would have removed from this frame. Logged, not
        # applied. ACT_MAX 0.60 is inert at night (3 frames of 493 on 1 Sep)
        # and 0.30 is the first candidate worth measuring.
        veto30 = int((raw_blocks & (best["act"] >= 0.30)).sum())

        m   = blob_metrics(npix, blocks, block_peaks(src), best["act"])
        m["dist"] = bd                 # how well this frame matched its preset
        hit = is_hit(m, best["n"], t)
        log(f"[{self.name}] {lm} p{best['id']} n={best['n']} {mode} px={m['px']} "
            f"blob={m['blob']} {m['bw']}x{m['bh']} fill={m['fill']} dom={m['dom']} "
            f"nb={m['nb']} bact={m['bact']} veto={vetoed}/{veto30} "
            f"{'<== HIT' if hit else ''}")

        self.rows.append(dict(utc=now.strftime("%Y-%m-%d %H:%M:%S"), last_modified=lm,
                              preset=best["id"], n=best["n"], dist=round(bd, 1),
                              mode=mode, bright=round(bright, 1), px=m["px"],
                              blob=m["blob"], blob2=m["blob2"],
                              bw=m["bw"], bh=m["bh"], fill=m["fill"],
                              dom=m["dom"], dom2=m["dom2"], cx=m["cx"], cy=m["cy"],
                              bpk=m["bpk"], bsat=m["bsat"], bact=m["bact"],
                              nblobs=m["nb"], blocks=m["blocks"],
                              vetoed=vetoed, veto30=veto30,
                              hit=int(hit), bytes=len(raw)))

        if COLLECT == "all":
            self.archive(raw, stamp, best["id"], m)
        elif COLLECT == "top":
            self.keep.append((m["blob"], stamp, best["id"], m, raw))

        if hit:
            self.nhits += 1
            day = self.hits / now.strftime("%Y%m%d")
            day.mkdir(parents=True, exist_ok=True)
            (day / f"{now.strftime('%H%M%S')}_p{best['id']}_blob{m['blob']}.jpg"
             ).write_bytes(raw)
            self.notify(f"movement (preset {best['id']}, blob {m['blob']}, "
                        f"{m['bw']}x{m['bh']}, fill {m['fill']})", raw)

        best["bg"] = best["bg"] * (1 - t["EMA"]) + g * t["EMA"]

    def flush_keep(self):
        """In 'top' mode keep only the few most interesting frames of the run.
        Sorting a day's folder by name still ranks every candidate by blob."""
        for blob, stamp, pid, m, raw in sorted(self.keep, reverse=True,
                                               key=lambda k: k[0])[:TOP_N]:
            if blob:
                self.archive(raw, stamp, pid, m)


def main():
    log(f"http stack: {'curl_cffi impersonate=' + IMPERSONATE if _cc else 'requests (no TLS impersonation)'}")
    deadline = time.time() + RUNTIME
    ws = [Watcher(c) for c in CAMERAS]
    ts = [threading.Thread(target=w.run, args=(deadline,), daemon=False) for w in ws]
    # Stagger, so the cameras do not arrive at the host as a simultaneous burst.
    for i, th in enumerate(ts):
        if i:
            time.sleep(3)
        th.start()
    for th in ts:
        th.join()

    log("--- " + " | ".join(
        f"{w.name}: {len(w.presets)} presets, {w.nframes} frames, {w.nhits} hits"
        for w in ws))

    blocked = [w.name for w in ws if w.forbidden]
    if blocked:
        log(f"\n*** {FORBID_MAX} consecutive 403s from the image host for: "
            + ", ".join(blocked) + " ***\n"
            "Not necessarily an IP block: with curl_cffi the same runner reached\n"
            "other cameras on 30 Aug 2026. Check the camera's own URL in a browser\n"
            "before concluding the route is dead.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
