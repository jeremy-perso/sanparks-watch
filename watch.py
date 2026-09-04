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
PRESET_CAP  = 200        # refuse to learn more views than this
#
# 120 -> 200 ON 4 SEP 2026, AS INSURANCE FOR THE TALAMATI SIG_TOL CHANGE, NOT
# AS A FIX FOR ANYTHING. SIG_TOL 25 -> 11 at Talamati will fork a new preset on
# the 23.2% of its rows that sit above dist 11 (measured, 1,638 rows of 3-4
# Sep), and Talamati already reached preset id 127 in 29 hours at SIG_TOL 25.
# Eviction is least-recently-seen and the comment below explains why the old
# presets are the load-bearing ones, so an eviction storm during the first day
# of the experiment would confound exactly the measurement the change exists to
# make. Cost is Actions cache: backgrounds are ~330 KB each, so 200 presets per
# camera is about 66 MB against 40 MB, on a 10 GB repo cache limit.
#
# THIS IS A CEILING, NOT A TARGET. If Talamati is still creating presets fast
# enough to approach 200 after two days, SIG_TOL 11 is the wrong value here and
# the answer is to reconsider it, not to raise the cap again.
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
                # Vertical position ceiling on the blob centroid, as a fraction
                # of frame height. 1.01 is INERT (cy can never exceed 1.00), so
                # every camera and mode that does not override this behaves
                # exactly as before. Nossob thr_night sets it; see cameras.py.
                CY_MAX=1.01,
                # per-preset activity veto: blocks that change this often are
                # scenery that always moves (grass, leaves) and are ignored.
                #
                # ACT_MAX IS NOT A HIT GATE AND MUST NOT BE REUSED AS ONE.
                # It selects which blocks are allowed to form a blob at all, so
                # lowering it changes blob, fill, dom, nblobs and cy on every
                # frame. The 2 Sep notes proposed "ACT_MAX 0.21" meaning a
                # ceiling on the LOGGED `bact` column; that is BACT_MAX below.
                # Setting this one to 0.21 would silently re-cut every blob in
                # the archive and invalidate every threshold measured on it.
                ACT_MAX=0.60, ACT_MIN_N=12, ACT_EMA=0.06,
                # Ceiling on `bact`: the mean per-preset activity score of the
                # blob's OWN blocks. High means the blob sits where this view
                # always moves (grass, a trough rim that flickers with the
                # floodlight), which is scenery; an animal stands somewhere the
                # background is normally still. 1.01 is INERT, since bact is a
                # mean of EMA values that cannot exceed 1.0, so every camera and
                # mode that does not override this behaves exactly as before.
                # Nossob thr_night sets it; see cameras.py for the measurement.
                BACT_MAX=1.01,
                # Ceiling on `bsat`: the share of the blob's blocks whose SOURCE
                # peak pixel touches 250. High means the blob is a cluster of
                # blown-out point sources, which at Nossob is a floodlit insect.
                # 1.01 is INERT (bsat is a share, max 1.00). MEASURED BUT NOT
                # DEPLOYED as of 2 Sep 2026: see the note in cameras.py.
                SAT_MAX=1.01)

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
CSV_COLS = ["utc", "last_modified", "preset", "n", "dist", "dist2", "mode",
            "bright", "px", "pxlo", "edge", "blob", "blob2", "bw", "bh", "fill",
            "dom", "dom2", "cx", "cy", "bpk", "bsat", "bact", "nblobs",
            "blocks", "vetoed", "veto30", "hit", "bytes"]

# --- THREE INSTRUMENTATION COLUMNS ADDED 4 SEP 2026 --------------------------
# NONE OF THEM CHANGES A DECISION. `is_hit` does not read any of them. They
# exist because three open questions in the notes cannot be answered by
# replaying the existing log, and each one is cheaper to measure than to argue
# about.
#
# `pxlo` -- PIXELS CHANGED AT PIX_THR_LO INSTEAD OF PIX_THR.
#   THE QUESTION: is Satara blind at night because of PIX_THR, or because
#   nothing is there? Measured 3-4 Sep, Satara night `px` median is 27 changed
#   pixels out of ~75,000 visible, `blob` is exactly 0 in 57.4% of rows and
#   under 3 in 73.3%, while `bright` is 49 and consecutive JPEGs differ by a
#   median of 10.7 KB. So frames are arriving, they are lit, and they are
#   changing on disk.
#   THE FRAME THAT FORCED THIS: frames/satara/20260903/224903_p3_blob0002.jpg
#   shows a dark four-legged animal about 9.6 x 6.4 blocks walking across open
#   ground, legs and body outline legible to the eye, and the row reads px 49,
#   blob 2. No value of BLOB_MIN, NB_MAX, DIST_MAX, FILL or DOM reaches that
#   frame. PIX_THR is two steps upstream of all of them.
#   WHY IT CANNOT BE REPLAYED: px is computed inside change_blocks from the
#   pixels, which are not in the CSV.
#   HOW TO READ IT: on Satara night rows, pxlo/px. If it is near 1 the scene
#   really is static and PIX_THR is innocent. If pxlo is 10x to 100x px on the
#   frames where an animal is visible, PIX_THR 24 is the gate and a night-only
#   PIX_THR is the next change at that camera.
#
# `edge` -- MEAN ABSOLUTE HORIZONTAL GRADIENT OF THE ANALYSIS FRAME.
#   THE QUESTION: how many frames are captured while the camera is panning?
#   frames/satara/20260904/013209_p38_blob0425.jpg is visibly motion-smeared
#   across every edge. Its row is n=2, px 14,419, nblobs 130: a brand-new
#   preset, a huge change count, a meaningless blob, and it never recurs. A
#   mid-pan capture is a triple cost -- it mints a preset, it burns a MIN_N
#   deaf window (five species have already been lost to MIN_N), and it pollutes
#   whichever background it lands in.
#   HOW TO READ IT: `edge` should be roughly stable within a preset. A frame
#   30-50% below its preset's usual `edge` is blurred. If that class is more
#   than a percent or two of frames, a blur reject in handle() pays for itself,
#   and it is a rejection that costs no recall because there is nothing legible
#   in the frame to lose.
#
# `dist2` -- MATCH DISTANCE TO THE SECOND-BEST PRESET.
#   THE QUESTION: SIG_TOL is being changed at Talamati today on the strength of
#   the `dist` column, which is the distance to the BEST preset. `dist2` says
#   how much better the best one was. A frame with dist 3 and dist2 4 is
#   ambiguous between two presets and is being assigned arbitrarily; a frame
#   with dist 3 and dist2 30 is unambiguous.
#   HOW TO READ IT: dist2 - dist, the margin. If Talamati's margin is wide
#   after the SIG_TOL change, the split is clean. If it is narrow, the new
#   presets are duplicates of each other and the change has traded one problem
#   for another. This is the number that says whether to keep 11 or go back.

PIX_THR_LO = 12          # only ever used to compute `pxlo`. Never a decision.


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
    # INSTRUMENTATION ONLY, added 4 Sep 2026. Mean absolute horizontal gradient
    # of the analysis frame: a sharp frame has strong edges, a frame captured
    # mid-pan is smeared and its gradient collapses. Nothing reads this; it is
    # logged so the size of the mid-pan class can be counted before anyone
    # writes a reject for it. One diff over a 384x216 array per frame.
    edge = float(np.abs(np.diff(g, axis=1)).mean())
    return g, s, bright, src, edge


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
    """Per-pixel change, folded into the BLK x BLK block grid.

    Returns (px, pxlo, blocks). `pxlo` is the same count at PIX_THR_LO and is
    INSTRUMENTATION ONLY: nothing downstream reads it and no decision uses it.
    See the CSV_COLS note. The absolute difference array is computed once and
    thresholded twice, so this costs one extra comparison over the 384x216
    array per frame and nothing else."""
    ad = np.abs(g - bg)
    d = (ad > t["PIX_THR"]) & MASK
    lo = (ad > PIX_THR_LO) & MASK
    blocks = (d.reshape(BH, BLK, BW, BLK).sum(axis=(1, 3)) >= t["BLK_MIN"]) & BMASK
    return int(d.sum()), int(lo.sum()), blocks


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

    m may carry `dist` (distance to the matched preset), `nb` (how many blobs
    the change broke into), `cy` (where the blob sits vertically), `bact` (how
    restless the blob's own blocks normally are) and `bsat` (how much of it is
    blown out). All default to a passing value so that older callers and the
    archived selftest rows behave exactly as before.

    The gates are ordered cheapest-first and the FIRST one to fire is the one
    that rejects a frame; more than one can be true at once. Worth remembering
    when diagnosing a specific miss."""
    if n_frames < t["MIN_N"]:                             return False
    if m.get("dist", 0.0) > t["DIST_MAX"]:                return False
    if m.get("nb", 1) > t["NB_MAX"]:                      return False
    if m.get("cy", 0.0) > t["CY_MAX"]:                    return False
    if m.get("bact", 0.0) > t["BACT_MAX"]:                return False
    if m.get("bsat", 0.0) > t["SAT_MAX"]:                 return False
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
        self.next_id = 0        # monotonic, so eviction never reuses an id
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
        self.next_id = int(meta.get("next_id", 0))
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
        self.next_id = max([self.next_id] + [m["id"] + 1 for m in self.presets])

    def save(self):
        keep = {m["id"] for m in self.presets}
        for f in self.state.glob("bg*.npy"):
            if int(f.stem[2:]) not in keep:
                f.unlink(missing_ok=True)
        for f in self.state.glob("act*.npy"):
            if int(f.stem[3:]) not in keep:
                f.unlink(missing_ok=True)
        for m in self.presets:
            np.save(self.state / f"bg{m['id']}.npy", m["bg"].astype(np.float16))
            np.save(self.state / f"act{m['id']}.npy", m["act"].astype(np.float16))
        (self.state / "presets.json").write_text(json.dumps({
            "etag": self.etag, "next_id": self.next_id,
            "presets": [{"id": m["id"], "sig": np.round(m["sig"], 2).tolist(),
                         "n": m["n"], "seen": m["seen"]} for m in self.presets]}, indent=1))

    def write_csv(self):
        if not self.rows:
            return
        day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        # The camera name is in the DIRECTORY and in the FILENAME on purpose.
        # The directory keeps the repo tidy; the filename survives being
        # downloaded. Before 2 Sep 2026 this was just `{day}.csv`, so pulling
        # today's log from every camera put three files called 20260902.csv in
        # one folder and they had to be renamed by hand before anything could
        # be analysed. With three cameras that is three renames per session.
        #
        # This starts NEW files. Any `logs/<cam>/YYYYMMDD.csv` already in the
        # repo stops being appended to at the moment this ships, so the day it
        # ships is split across two files for each camera. Nothing reads these
        # files in code, so no other change is needed.
        #
        # SCHEMA ROTATION, ADDED 4 SEP 2026. Three instrumentation columns went
        # in mid-day, so today's file already exists with the 26-column header
        # and csv.DictWriter would raise ValueError on the extra keys. Rather
        # than lose the rest of the day, if the header on disk does not match
        # CSV_COLS we roll to `{day}_{cam}_v2.csv`, `_v3` and so on. The old
        # file is left exactly as it is.
        #
        # This is not a workaround to be removed. The schema has changed four
        # times in six days and it will change again; every previous change
        # either silently corrupted a day or had to be timed to a midnight.
        f = self._csv_path(day)
        new = not f.exists()
        with f.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLS)
            if new:
                w.writeheader()
            w.writerows(self.rows)

    def _csv_path(self, day):
        """Today's log, rolled to a new suffix if the header on disk is a
        different schema from CSV_COLS."""
        base = self.logs / f"{day}_{self.name}.csv"
        for cand in [base] + [self.logs / f"{day}_{self.name}_v{i}.csv"
                              for i in range(2, 20)]:
            if not cand.exists():
                return cand
            try:
                with cand.open(newline="") as fh:
                    hdr = next(csv.reader(fh), [])
            except OSError:
                return cand
            if hdr == CSV_COLS:
                return cand
            if cand is base:
                log(f"[{self.name}] log schema changed ({len(hdr)} cols on "
                    f"disk, {len(CSV_COLS)} now); rolling to a new file")
        return self.logs / f"{day}_{self.name}_v20.csv"

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
                    # BREAK, DO NOT RETURN. Returning here used to skip save(),
                    # flush_keep() and write_csv(), so a camera that got blocked
                    # at minute 8 of a 9-minute run threw away every row and
                    # every archived frame it had already collected, and lost
                    # the preset backgrounds it had just learned. Found 2 Sep
                    # 2026 while adding a third camera: with three cameras on
                    # one host this path is hit more often, and the frames
                    # before a block are exactly the ones worth keeping.
                    self.forbidden = True
                    break
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
        g, sig, bright, src, edge = analyse(raw)
        self.nframes += 1

        # bd2 is the distance to the SECOND-best preset. Instrumentation only:
        # nothing branches on it. bd2 - bd is the margin, and a narrow margin
        # means the frame was assigned to one of two near-identical presets
        # more or less arbitrarily. That is the number that says whether a
        # SIG_TOL value is splitting real views or minting duplicates.
        best, bd, bd2 = None, 1e9, 1e9
        for m in self.presets:
            d = float(np.abs(sig - m["sig"]).mean())
            if d < bd:
                best, bd, bd2 = m, d, bd
            elif d < bd2:
                bd2 = d

        if best is None or bd > t["SIG_TOL"]:
            # AT THE CAP, EVICT, DO NOT DROP THE FRAME.
            #
            # This used to `return`, which meant no CSV row, no background
            # update and no chance of a hit. Measured 30 Aug - 1 Sep 2026:
            # Nossob reached preset id 60 and Talamati 56 in three days, about
            # 25 new ids a day each, so a cap of 120 lands within days and from
            # then on every unmatched frame would vanish silently.
            #
            # Evicting the least-recently-seen preset is safe because the
            # working set is small and stable: 76% of 1 Sep's Nossob frames
            # landed on presets born on 30 or 31 Aug, and the presets that get
            # evicted are the ones nothing has matched for the longest. It is
            # also why PRESET_TTL must NOT be shortened to control growth: the
            # old presets are the load-bearing ones.
            if len(self.presets) >= PRESET_CAP:
                victim = min(self.presets, key=lambda p: p.get("seen", 0))
                self.presets.remove(victim)
                for f in (self.state / f"bg{victim['id']}.npy",
                          self.state / f"act{victim['id']}.npy"):
                    f.unlink(missing_ok=True)
                log(f"[{self.name}] {lm} preset cap {PRESET_CAP} reached, "
                    f"evicted p{victim['id']} (n={victim['n']}, unseen "
                    f"{(time.time() - victim.get('seen', 0)) / 3600:.1f}h)")
            best = {"id": self.next_id,
                    "sig": sig, "bg": g.copy(), "n": 1, "seen": time.time(),
                    "act": np.zeros((BH, BW), dtype=np.float32)}
            self.next_id += 1
            self.presets.append(best)
            log(f"[{self.name}] {lm} new preset p{best['id']} "
                f"(nearest {bd:.1f}, next {bd2:.1f}, edge {edge:.1f})")
            return

        best["n"] += 1
        best["seen"] = time.time()
        best["sig"] = best["sig"] * 0.7 + sig * 0.3

        npix, npixlo, raw_blocks = change_blocks(g, best["bg"], t)

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
        log(f"[{self.name}] {lm} p{best['id']} n={best['n']} {mode} "
            f"d={bd:.1f}/{min(bd2, 999.9):.1f} edge={edge:.1f} "
            f"px={m['px']}/{npixlo} "
            f"blob={m['blob']} {m['bw']}x{m['bh']} fill={m['fill']} dom={m['dom']} "
            f"nb={m['nb']} bact={m['bact']} veto={vetoed}/{veto30} "
            f"{'<== HIT' if hit else ''}")

        self.rows.append(dict(utc=now.strftime("%Y-%m-%d %H:%M:%S"), last_modified=lm,
                              preset=best["id"], n=best["n"], dist=round(bd, 1),
                              dist2=round(min(bd2, 999.9), 1),
                              mode=mode, bright=round(bright, 1), px=m["px"],
                              pxlo=npixlo, edge=round(edge, 2),
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
