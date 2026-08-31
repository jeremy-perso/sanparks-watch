#!/usr/bin/env python3
"""
Regression test for the decision rule.

Every row below is a real measurement, not a guess:

  NATURAL  - the largest blob found in a real frame with no animal in it.
             Any of these that scores a hit is a false positive.
  INJECTED - the same pipeline run on a real frame and its real learned
             background with a synthetic elliptical target added, so the
             geometry is what the detector would actually see.

Sources: Nossob night 24 Aug 2026 (in the handover notes); Nossob and Talamati
daylight 30 Aug 2026, 13:39-14:07 UTC, both cameras watched simultaneously.

Run it after touching cameras.py or is_hit:   python selftest.py
"""
import sys
from cameras import CAMERAS
from watch import is_hit, thresholds

CAMS = {c["name"]: c for c in CAMERAS}
BIG_N = 99                     # past every MIN_N, so geometry is what is tested


def M(blob, bw, bh, fill, dom, dist=0.0, nb=1):
    """dist and nb default to passing values, so every row measured before
    31 Aug 2026 is tested against exactly the rule it was measured under."""
    return dict(blob=blob, bw=bw, bh=bh, fill=fill, dom=dom, dist=dist, nb=nb)


# --- empty waterholes: every one of these must be rejected -------------------
NATURAL = {
    ("nossob", "day"): [
        M(14, 7, 5, 0.40, 0.13), M(14, 6, 8, 0.29, 0.13), M(7, 5, 3, 0.47, 0.19),
        M(2, 1, 2, 1.00, 0.14),  M(15, 4, 6, 0.63, 0.15), M(2, 2, 1, 1.00, 0.18),
        M(4, 3, 3, 0.44, 0.57),  M(14, 4, 6, 0.58, 0.13), M(6, 4, 3, 0.50, 0.18),
        M(11, 5, 3, 0.73, 0.20), M(66, 28, 4, 0.59, 0.40), M(86, 21, 15, 0.27, 0.55),
        M(2, 1, 2, 1.00, 0.25),  M(268, 45, 16, 0.37, 0.56), M(20, 8, 4, 0.63, 0.15),
        M(10, 6, 4, 0.42, 0.10), M(36, 15, 6, 0.40, 0.27), M(14, 6, 4, 0.58, 0.09),
    ],
    # the six smears and the scatter case from the 24 Aug night calibration
    ("nossob", "night"): [
        M(76, 76, 15, 0.37, 0.80), M(47, 47, 12, 0.44, 0.70), M(38, 38, 10, 0.46, 0.70),
        M(36, 36, 12, 0.29, 0.60), M(32, 32, 5, 0.46, 0.60),  M(29, 29, 6, 0.40, 0.60),
        M(14, 14, 10, 0.50, 0.33),
    ],
    ("talamati", "day"): [
        M(1, 1, 1, 1.00, 0.50),   M(1, 1, 1, 1.00, 1.00),   M(147, 24, 16, 0.38, 0.47),
        M(107, 33, 9, 0.36, 0.29), M(455, 63, 18, 0.40, 0.59), M(249, 41, 14, 0.43, 0.40),
        M(58, 26, 5, 0.45, 0.25), M(70, 26, 7, 0.38, 0.50),  M(39, 15, 9, 0.29, 0.17),
        M(249, 40, 12, 0.52, 0.44), M(65, 20, 5, 0.65, 0.48), M(101, 22, 16, 0.29, 0.37),
        M(129, 46, 7, 0.40, 0.83),
    ],
}

# --- CONFIRMED, 30-31 Aug 2026: real frames, eyes on the JPEG ----------------
# Nossob after dark. Every row here was archived, looked at, and either does or
# does not contain an animal. This is the first non-synthetic sensitivity test
# the project has had. dist and nb are the real logged values.
REAL_ANIMAL = {
    ("nossob", "night"): [
        ("jackal at the water, side on", M(51, 9, 10, 0.57, 0.98, 5.2, 2)),
        ("small canid, far bank, broadside", M(20, 11, 4, 0.45, 0.50, 2.0, 8)),
        ("same canid, drinking", M(6, 3, 3, 0.67, 0.46, 1.4, 4)),
        ("jackal walking, upper left", M(18, 8, 4, 0.56, 0.64, 0.6, 5)),
        ("jackal at the right edge", M(28, 11, 7, 0.36, 0.58, 1.8, 10)),
        ("owl on the bank", M(5, 3, 2, 0.83, 1.00, 0.4, 1)),
        ("owl on the trough rim", M(14, 4, 5, 0.70, 0.88, 0.5, 2)),
        ("jackal drinking, insects in frame", M(16, 7, 4, 0.57, 0.36, 1.7, 12)),
    ],
    ("nossob", "day"): [
        ("dove flock, hit 1", M(48, 12, 7, 0.57, 0.22, 1.7, 17)),
        ("dove flock, hit 2", M(77, 15, 12, 0.43, 0.40, 1.6, 16)),
    ],
}
# how many of the above we currently catch. The drinking jackal at dom 0.36 is
# the one we knowingly give up: recovering it needs DOM_MIN 0.35, which on this
# same log let in 13 extra tiny night blobs. Revisit when dom2 has been logged
# for a few nights. The doves are day-mode, where DOM_MIN is already 0.
REAL_MIN = {("nossob", "night"): 7, ("nossob", "day"): 2}

# --- CONFIRMED empty: real frames, eyes on the JPEG, nothing in them ---------
# The four Nossob dawn hits of 31 Aug (sun rising while the IR-cut filter swaps
# in, so every background is stale at once) and one night insect.
CONFIRMED_FP = {
    ("nossob", "day"): [
        ("dawn 06:21 local", M(207, 52, 5, 0.80, 0.46, 7.8, 9)),
        ("dawn 06:48 local", M(61, 13, 6, 0.78, 0.26, 4.9, 48)),
        ("dawn 07:18 local", M(58, 15, 8, 0.48, 0.13, 3.6, 103)),
        ("dawn 07:38 local", M(308, 61, 7, 0.72, 0.68, 4.7, 52)),
    ],
    # Every Talamati night hit that survived the 31 Aug gates was archived and
    # looked at. All nine were out-of-focus insects near the lens.
    ("talamati", "night"): [
        ("insects in the IR floodlight", M(31, 7, 6, 0.74, 0.55, 2.5, 9)),
        ("insects, second frame", M(17, 6, 5, 0.57, 0.44, 3.1, 11)),
        ("preset 9 against a smeared background", M(880, 47, 44, 0.43, 0.87, 10.0, 32)),
        ("overexposed blowout", M(106, 6, 23, 0.77, 0.88, 3.8, 7)),
        ("insect disc, p7 18:36", M(46, 9, 8, 0.64, 0.40, 3.8, 8)),
        ("insect disc, p12 18:44", M(57, 8, 10, 0.71, 0.44, 4.3, 21)),
        ("insect disc, p10 19:02", M(66, 9, 9, 0.81, 0.79, 3.4, 2)),
        ("insect disc, p14 19:03", M(81, 10, 12, 0.68, 0.60, 4.8, 15)),
        ("insect disc, p14 19:04", M(74, 9, 11, 0.75, 0.68, 3.3, 8)),
        ("insect disc, p14 19:13", M(67, 9, 10, 0.74, 0.60, 2.6, 13)),
        ("insect disc, p14 19:28", M(56, 9, 9, 0.69, 0.72, 3.5, 8)),
        ("insect disc, p14 19:32", M(50, 8, 8, 0.78, 0.62, 4.5, 13)),
        ("insect disc, p14 04:59", M(78, 11, 11, 0.64, 0.42, 5.8, 5)),
    ],
}

# --- synthetic animals injected into real frames -----------------------------
INJECTED = {
    ("nossob", "day", "gemsbok 200x140"): [
        M(85, 18, 10, 0.47, 0.45), M(49, 10, 10, 0.49, 0.28), M(53, 13, 10, 0.41, 0.37),
        M(68, 13, 10, 0.52, 0.43), M(79, 20, 10, 0.40, 0.45), M(96, 20, 10, 0.48, 0.50),
        M(55, 9, 11, 0.56, 0.28),  M(83, 16, 11, 0.47, 0.39),
    ],
    # the jackal never becomes the largest blob in daylight: these are the
    # untouched natural blobs, recorded to document the limit, not to pass.
    ("nossob", "day", "jackal 80x55"): [
        M(20, 8, 4, 0.63, 0.15), M(20, 8, 4, 0.63, 0.14), M(10, 6, 4, 0.42, 0.09),
        M(13, 6, 3, 0.72, 0.12), M(36, 15, 6, 0.40, 0.26), M(36, 15, 6, 0.40, 0.25),
        M(14, 6, 4, 0.58, 0.09), M(14, 6, 4, 0.58, 0.09),
    ],
    ("talamati", "day", "elephant 400x300"): [
        M(318, 24, 24, 0.55, 0.48), M(321, 30, 24, 0.45, 0.42), M(252, 20, 18, 0.70, 0.49),
        M(302, 34, 20, 0.44, 0.73), M(246, 20, 16, 0.77, 0.54),
    ],
    ("talamati", "day", "gemsbok 200x140"): [
        M(163, 23, 20, 0.35, 0.32), M(196, 37, 11, 0.48, 0.34), M(87, 26, 7, 0.48, 0.26),
        M(59, 10, 7, 0.84, 0.26),   M(62, 11, 7, 0.81, 0.22),
    ],
}

# what we accept today. Anything better is a bonus, anything worse is a bug.
EXPECT_MIN = {
    ("nossob", "day", "gemsbok 200x140"):   8,
    ("nossob", "day", "jackal 80x55"):      0,
    ("talamati", "day", "elephant 400x300"): 5,
    ("talamati", "day", "gemsbok 200x140"):  1,
}


def thr_for(cam, mode):
    return thresholds(CAMS[cam], 13 if mode == "day" else 22)


def main():
    bad = 0

    print("false positives on real empty-waterhole frames")
    for (cam, mode), rows in NATURAL.items():
        fp = [m for m in rows if is_hit(m, BIG_N, thr_for(cam, mode))]
        flag = "FAIL" if fp else "ok  "
        print(f"  {flag} {cam:9s} {mode:5s} {len(fp)}/{len(rows)}")
        for m in fp:
            print(f"         leaked: blob{m['blob']} {m['bw']}x{m['bh']} "
                  f"fill={m['fill']} dom={m['dom']}")
        bad += len(fp)

    print("\ndetection of injected targets")
    for (cam, mode, label), rows in INJECTED.items():
        got = sum(is_hit(m, BIG_N, thr_for(cam, mode)) for m in rows)
        want = EXPECT_MIN[(cam, mode, label)]
        ok = got >= want
        bad += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {cam:9s} {mode:5s} {label:18s} "
              f"{got}/{len(rows)} detected (need >= {want})")

    print("\nCONFIRMED animals in real frames (30-31 Aug 2026)")
    for (cam, mode), rows in REAL_ANIMAL.items():
        got = sum(is_hit(m, BIG_N, thr_for(cam, mode)) for _, m in rows)
        want = REAL_MIN[(cam, mode)]
        ok = got >= want
        bad += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {cam:9s} {mode:5s} "
              f"{got}/{len(rows)} detected (need >= {want})")
        for label, m in rows:
            if not is_hit(m, BIG_N, thr_for(cam, mode)):
                print(f"         missed: {label}")

    print("\nCONFIRMED empty in real frames: any hit here is a false positive")
    for (cam, mode), rows in CONFIRMED_FP.items():
        fp = [l for l, m in rows if is_hit(m, BIG_N, thr_for(cam, mode))]
        print(f"  {'FAIL' if fp else 'ok  '} {cam:9s} {mode:5s} {len(fp)}/{len(rows)}")
        for l in fp:
            print(f"         leaked: {l}")
        bad += len(fp)

    print("\nsanity: night config still rejects the 24 Aug smears, and a "
          "gemsbok-sized\n        night blob still passes")
    night = thr_for("nossob", "night")
    gem_night = M(120, 14, 11, 0.78, 0.85)
    if not is_hit(gem_night, BIG_N, night):
        print("  FAIL nossob night no longer detects a clean gemsbok blob")
        bad += 1
    else:
        print("  ok   nossob night still detects a clean gemsbok blob")

    print("\nFAILURES:" if bad else "\nall checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
