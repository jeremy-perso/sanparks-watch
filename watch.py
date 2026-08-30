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
TOP_N   = int(os.getenv("TOP_N", 3))              # frames kept per run in 'top'
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
PRESET_CAP  = 40        # refuse to learn more views than this
PRESET_TTL  = 7 * 86400 # forget a preset unseen for this long

# --- inherited thresholds; cameras.py overrides what differs
DEFAULTS = dict(SIG_TOL=11, PIX_THR=24, BLK_MIN=6, MIN_N=4, BLOB_MIN=3,
                BLOB_MAX=600, DOM_MIN=0.45, ASP_MAX=2.4, FILL_CMP=0.32,
                FILL_WIDE=0.62, EMA=0.25,
                # per-preset activity veto: blocks that change this often are
                # scenery that always moves (grass, leaves) and are ignored
                ACT_MAX=0.60, ACT_MIN_N=12, ACT_EMA=0.06)

ROOT  = pathlib.Path(__file__).parent
NTFY  = os.getenv("NTFY_TOPIC", "")
# A truncated "Mozilla/5.0" is a bot tell. This is a full desktop Chrome set.
# UNMEASURED as a fix: if Cloudflare is blocking the runner's IP range rather
# than its headers, none of this helps. See the 403 result of 30 Aug 2026.
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
# UNMEASURED as a fix. Two 403s so far (GitHub Actions 30 Aug 2026, wsrv.nl
# same day) are confounded: both came from a datacenter IP AND a non-browser
# TLS stack. This is the test that separates those two explanations.
IMPERSONATE = os.getenv("IMPERSONATE", "chrome")
try:
    from curl_cffi import requests as _cc
except ImportError:
    _cc = None


CSV_COLS = ["utc", "last_modified", "preset", "n", "dist", "mode", "bright",
            "px", "blob", "bw", "bh", "fill", "dom", "nblobs", "blocks",
            "vetoed", "hit", "bytes"]


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
    The mean is taken over visible pixels only, so the clock cannot drag it."""
    im = Image.open(io.BytesIO(raw)).convert("L")
    g = np.asarray(im.resize((W, H)), dtype=np.float32)
    bright = float(g[MASK].mean())
    g = g - bright
    s = np.asarray(im.resize((SW, SH)), dtype=np.float32)
    s = s - s.mean()
    return g, s, bright


def change_blocks(g, bg, t):
    """Per-pixel change, folded into the BLK x BLK block grid."""
    d = (np.abs(g - bg) > t["PIX_THR"]) & MASK
    blocks = (d.reshape(BH, BLK, BW, BLK).sum(axis=(1, 3)) >= t["BLK_MIN"]) & BMASK
    return int(d.sum()), blocks


def blob_metrics(npix, blocks):
    """Largest connected region of change, described so animals separate from
    light: size, solidity, aspect, and how much of the change it accounts for."""
    lab, k = ndimage.label(blocks, structure=NB8)
    if k == 0:
        return dict(px=npix, blob=0, bw=1, bh=1, fill=0.0, dom=0.0, nb=0, blocks=0)
    sizes = ndimage.sum(blocks, lab, range(1, k + 1))
    top = int(np.argmax(sizes)) + 1
    ys, xs = np.nonzero(lab == top)
    bw, bh = int(np.ptp(xs) + 1), int(np.ptp(ys) + 1)   # numpy 2.0: no arr.ptp()
    n = int(sizes[top - 1])
    return dict(px=npix, blob=n, bw=bw, bh=bh,
                fill=round(n / (bw * bh), 2),
                dom=round(n / float(sizes.sum()), 2),
                nb=k, blocks=int(sizes.sum()))


def is_hit(m, n_frames, t):
    """Rejects the two real failure modes: a long flat smear where the light
    shifts, and change scattered across dozens of small blobs (wind, gain
    drift). A blob only counts if it is big enough, dominant, and solid."""
    if n_frames < t["MIN_N"]:                             return False
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
        g, sig, bright = analyse(raw)
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

        m   = blob_metrics(npix, blocks)
        hit = is_hit(m, best["n"], t)
        log(f"[{self.name}] {lm} p{best['id']} n={best['n']} {mode} px={m['px']} "
            f"blob={m['blob']} {m['bw']}x{m['bh']} fill={m['fill']} dom={m['dom']} "
            f"nb={m['nb']} veto={vetoed} {'<== HIT' if hit else ''}")

        self.rows.append(dict(utc=now.strftime("%Y-%m-%d %H:%M:%S"), last_modified=lm,
                              preset=best["id"], n=best["n"], dist=round(bd, 1),
                              mode=mode, bright=round(bright, 1), px=m["px"],
                              blob=m["blob"], bw=m["bw"], bh=m["bh"], fill=m["fill"],
                              dom=m["dom"], nblobs=m["nb"], blocks=m["blocks"],
                              vetoed=vetoed, hit=int(hit), bytes=len(raw)))

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
