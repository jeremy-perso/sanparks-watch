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
daylight 30 Aug 2026, 13:39-14:07 UTC, both cameras watched simultaneously;
Nossob and Talamati nights of 30-31 Aug and 31 Aug - 1 Sep; and the night of
1/2 Sep 2026, the first night on the 26-column schema and so the only source of
`bact` and `bsat` in this file.

Run it after touching cameras.py or is_hit:   python selftest.py
"""
import sys
from cameras import CAMERAS
from watch import is_hit, thresholds

CAMS = {c["name"]: c for c in CAMERAS}
BIG_N = 99                     # past every MIN_N, so geometry is what is tested


def M(blob, bw, bh, fill, dom, dist=0.0, nb=1, cy=0.0, bact=0.0, bsat=0.0):
    """dist, nb, cy, bact and bsat all default to passing values, so every row
    measured before the column existed is tested against exactly the rule it
    was measured under. cy is the blob centroid as a fraction of frame height,
    logged from 31 Aug 2026 12:48 UTC; the 24 Aug rows below have none. bact
    and bsat are logged from the 1 Sep bundle (26 columns) and exist only on
    the night of 1/2 Sep and later, so every row above that block defaults to
    0.0 and is untested against BACT_MAX and SAT_MAX. That is a convention,
    not evidence: those rows do not vote on either gate."""
    return dict(blob=blob, bw=bw, bh=bh, fill=fill, dom=dom, dist=dist, nb=nb,
                cy=cy, bact=bact, bsat=bsat)


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

# --- CONFIRMED, 30 Aug - 2 Sep 2026: real frames, eyes on the JPEG -----------
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
        # --- 30 Aug 2026, added 2 Sep after the archived hits of that night
        # were pulled back and looked at for the first time. These three were
        # already being caught; they were simply never written down.
        #
        # The SPRINGBOK is the first confirmed antelope at Nossob at night and
        # the first confirmed animal here that is neither a canid nor an owl.
        # It matters for BLOB_MIN: a whole springbok, side on and head down at
        # the trough, measures 20 blocks. Anything above about 8 loses it.
        ("SPRINGBOK at the trough, 30 16:46:10Z", M(20, 8, 4, 0.62, 0.77, 4.2, 4)),
        ("canid broadside, far bank, 30 18:08:13Z", M(3, 3, 1, 1.00, 1.00, 0.4, 1)),
        ("owl on the bank, second frame, 30 18:54:05Z", M(5, 3, 2, 0.83, 1.00, 0.3, 1)),
        # --- 31 Aug - 1 Sep 2026. All 77 hits of that night were archived and
        # looked at; these nine contain animals. The lion is the project's
        # first large predator and the first four-frame sequence of one animal
        # across three presets. Times are the UTC CSV row; the burnt-in clock
        # reads about 8 minutes earlier.
        #
        # Note the range: the SAME lion in the SAME minute measures 524 blocks
        # on a close preset and 3 on a wide one. This is why Nossob night
        # BLOB_MIN is 3 and why raising it is not the answer to a noisy log.
        ("jackal at the trough, side on, 31 17:53:17Z", M(10, 6, 3, 0.56, 0.50, 1.0, 9, 0.333)),
        ("canid at the tree base, probable jackal, 31 21:25:52Z", M(10, 5, 4, 0.50, 0.91, 0.3, 2, 0.698)),
        ("jackal standing, facing camera, 31 22:54:01Z", M(6, 4, 3, 0.50, 1.00, 0.4, 1, 0.667)),
        ("jackal drinking, with reflection, 31 22:55:55Z", M(74, 16, 12, 0.39, 0.52, 2.0, 14, 0.195)),
        ("owl on the bank, eyeshine, 31 23:21:08Z", M(4, 2, 3, 0.67, 1.00, 0.5, 1, 0.440)),
        ("LION drinking, wide framing, 01 01:56:57Z", M(141, 24, 14, 0.42, 0.98, 1.8, 4, 0.309)),
        ("LION drinking, close framing, 01 01:57:09Z", M(524, 48, 29, 0.38, 0.96, 5.4, 8, 0.227)),
        ("lion, third preset, 01 01:58:59Z", M(5, 3, 3, 0.56, 0.83, 0.8, 2, 0.537)),
        ("lion, leaving, 01 01:59:11Z", M(3, 2, 2, 0.75, 0.75, 0.6, 2, 0.531)),

        # --- NIGHT OF 1/2 SEP 2026, added 2 Sep. The first night on the
        # 26-column schema, so these are the only rows in this file carrying
        # bact and bsat, and the only rows that can score BACT_MAX or SAT_MAX.
        #
        # Every row here comes from the archived CSV and is documented in
        # animals.md with a cx/cy/bw/bh box that lands on the animal. Two
        # frames that contain animals are NOT here:
        #   01 20:36:59 p16 blob 433. A lion is unmistakably drinking, but the
        #     logged blob is 61x23 blocks (1220x460 px) centred on the whole
        #     lit sand bar while the animal is about 140x70 px. Not a row
        #     measuring the animal.
        #   01 21:55:52 p15 blob 3 and 02 00:34:13 p15 blob 18. Small shapes
        #     with eyeshine on the trough rim, counted as animals in the
        #     night's recall but given no bw/bh in animals.md, so the box has
        #     never been checked. Both currently score hits. Add them the
        #     moment the box is drawn and confirmed.
        #
        # THE LION IS 19 FRAMES ACROSS THREE VISITS and at least two
        # individuals. Note the spread again: 9 blocks on p14 and 186 on p8
        # inside the same minute.
        ("LION visit 1, 01 19:44:57Z", M(116, 13, 18, 0.50, 0.57, 2.7, 11, 0.133, 0.060, 0.00)),
        ("LION visit 1, 01 19:45:08Z", M(112, 15, 15, 0.50, 0.48, 2.9, 13, 0.107, 0.060, 0.00)),
        ("LION visit 1, 01 19:46:07Z", M(21, 8, 7, 0.38, 0.88, 1.0, 2, 0.614, 0.063, 0.00)),
        ("LION visit 1, 01 19:46:54Z", M(9, 4, 3, 0.75, 1.00, 0.7, 1, 0.539, 0.127, 0.00)),
        ("LION visit 1, 01 19:47:17Z", M(81, 18, 11, 0.41, 0.74, 1.8, 11, 0.299, 0.061, 0.00)),
        ("LION visit 1, two animals, 01 19:47:52Z", M(186, 17, 23, 0.48, 0.78, 3.1, 6, 0.191, 0.093, 0.00)),
        ("LION visit 1, 01 19:48:04Z", M(136, 16, 20, 0.42, 0.74, 2.2, 6, 0.172, 0.147, 0.00)),
        ("LION visit 1, 01 19:48:16Z", M(119, 13, 16, 0.57, 0.58, 2.6, 10, 0.113, 0.102, 0.00)),
        ("LION visit 1, walking the rim, 01 19:48:52Z", M(39, 11, 8, 0.44, 0.97, 0.9, 2, 0.608, 0.090, 0.00)),
        ("LION visit 2, 01 20:36:01Z", M(38, 10, 7, 0.54, 1.00, 0.7, 1, 0.622, 0.063, 0.00)),
        ("LION visit 2, 01 20:36:12Z", M(37, 10, 7, 0.53, 1.00, 0.5, 1, 0.622, 0.119, 0.00)),
        ("LION visit 2, 01 20:37:11Z", M(142, 23, 14, 0.44, 0.89, 2.6, 9, 0.314, 0.062, 0.00)),
        ("LION visit 2, 01 20:38:58Z", M(58, 16, 8, 0.45, 0.98, 0.8, 2, 0.606, 0.134, 0.00)),
        ("LION visit 2, 01 20:39:09Z", M(36, 7, 7, 0.73, 0.80, 0.6, 3, 0.604, 0.199, 0.00)),
        ("LION visit 3, 02 01:40:00Z", M(156, 23, 11, 0.62, 1.00, 2.8, 1, 0.323, 0.064, 0.00)),
        ("LION visit 3, 02 01:40:12Z", M(139, 22, 11, 0.57, 1.00, 1.8, 1, 0.319, 0.119, 0.00)),
        ("LION visit 3, 02 01:42:10Z", M(9, 5, 3, 0.60, 1.00, 0.5, 1, 0.543, 0.081, 0.11)),
        ("LION visit 3, drinking side on, 02 01:42:57Z", M(134, 21, 11, 0.58, 0.99, 1.2, 2, 0.319, 0.166, 0.00)),
        # THE HIGHEST bact ON ANY CONFIRMED ANIMAL IN THE ARCHIVE: 0.209.
        # BACT_MAX 0.21 sits one tick above this single frame.
        ("LION visit 3, 02 01:43:08Z", M(121, 20, 11, 0.55, 0.99, 1.1, 2, 0.319, 0.209, 0.00)),

        # BARN OWL, resolved to species 2 Sep from the p63 frames: heart-shaped
        # facial disc, no ear tufts, fine speckling on buff upperparts.
        ("BARN OWL in the camelthorn, 01 21:06:06Z", M(91, 17, 14, 0.38, 0.62, 1.3, 13, 0.362, 0.110, 0.04)),
        ("BARN OWL in the camelthorn, 01 21:06:18Z", M(68, 16, 13, 0.33, 0.67, 0.9, 8, 0.362, 0.170, 0.06)),
        ("BARN OWL whole bird, 01 21:06:54Z", M(231, 23, 28, 0.36, 0.90, 2.8, 8, 0.458, 0.124, 0.00)),
        # TWO BARN OWLS on the concrete block, four eyeshine points in a 3x7
        # box. bsat 0.24 is the HIGHEST ON ANY CONFIRMED ANIMAL ANYWHERE, so it
        # is the hard floor under SAT_MAX. Anything below 0.25 takes the owls.
        ("TWO BARN OWLS, four eyeshine points, 01 23:46:58Z", M(17, 3, 7, 0.81, 0.89, 0.8, 2, 0.125, 0.062, 0.24)),
        ("BARN OWL, second frame, 01 23:47:10Z", M(9, 5, 3, 0.60, 0.60, 0.5, 3, 0.093, 0.091, 0.00)),

        ("black-backed jackal, 01 19:13:59Z", M(8, 4, 3, 0.67, 1.00, 0.8, 1, 0.718, 0.079, 0.00)),
        ("black-backed jackal, 01 19:14:11Z", M(8, 5, 4, 0.40, 1.00, 0.5, 1, 0.694, 0.094, 0.00)),
        ("black-backed jackal, 01 21:56:16Z", M(6, 3, 4, 0.50, 1.00, 0.4, 1, 0.654, 0.081, 0.00)),
        ("jackal drinking with reflection, 01 23:20:11Z", M(58, 8, 17, 0.43, 0.79, 1.3, 5, 0.325, 0.060, 0.02)),
        # Motion-blurred four-legged mammal leaving frame bottom left, roughly
        # jackal-sized. Not resolvable to species; the box lands on it.
        ("unresolved night mammal, 01 23:23:19Z", M(27, 7, 7, 0.55, 0.48, 1.2, 9, 0.759, 0.060, 0.00)),

        # HARE, THE ONE CONFIRMED MISS OF THE NIGHT, and a valid measured row:
        # the box lands exactly on the animal. Long ears laid back, compact
        # hunched body, sitting in short grass outside the floodlit strip.
        # It is rejected TWICE over by the live config: CY_MAX 0.85 fires first
        # at cy 0.859, and FILL_CMP 0.32 would reject it anyway at fill 0.31.
        # Left in deliberately so the cost of the fill floor and the position
        # gate is visible in this file rather than argued about in markdown.
        ("HARE, KNOWN MISS, 01 19:35:08Z", M(11, 7, 5, 0.31, 1.00, 0.4, 1, 0.859, 0.062, 0.00)),
    ],
    ("nossob", "day"): [
        ("dove flock, hit 1", M(48, 12, 7, 0.57, 0.22, 1.7, 17)),
        ("dove flock, hit 2", M(77, 15, 12, 0.43, 0.40, 1.6, 16)),
        # --- 1 Sep 2026, added 2 Sep. Three daylight frames where the logged
        # blob demonstrably lands ON the animal: the bounding box built from
        # cx/cy/bw/bh contains it. Frames that merely have an animal somewhere
        # while the blob is water glare are NOT here; see the notes.
        #
        # ALL THREE ARE CURRENTLY MISSED, and that is the point of adding
        # them. Daylight recall is now visible in this test instead of being
        # an argument in a markdown file. NB_MAX is what fails all three.
        ("BLUE WILDEBEEST pair drinking, 01 12:59:04Z", M(462, 58, 19, 0.42, 0.70, 9.8, 70, 0.322)),
        ("BATELEUR at the pan, 01 13:52:18Z", M(150, 16, 26, 0.36, 0.42, 3.2, 42, 0.381)),
        ("BATELEUR at the pan, wider preset, 01 13:55:14Z", M(270, 37, 28, 0.26, 0.62, 6.2, 46, 0.445)),
    ],
}
# how many of the above we currently catch. The 24 Aug drinking jackal at
# dom 0.36 is the one we knowingly give up: recovering it needs DOM_MIN 0.35,
# which on that log let in 13 extra tiny night blobs. dom2 was supposed to
# rescue it and cannot; see the comment on dom2 in watch.py. `blob2` is the
# next attempt and is logged from 1 Sep. The doves are day-mode, where DOM_MIN
# is already 0.
#
# NIGHT 19 of 20 as of 2 Sep 2026, up from 16 of 17: the springbok, the 30 Aug
# broadside canid and the second owl frame all pass unchanged.
#
# DAY IS DELIBERATELY 2 OF 5. The wildebeest pair and both bateleur frames are
# real confirmed daylight animals that this config does not catch. Raising
# this number is the goal of the daylight retune; it is a floor on what we
# have, not a claim about what we want.
#
# NIGHT 48 of 50 as of 2 Sep 2026 evening, up from 19 of 20. The denominator
# grew by the 30 rows of the night of 1/2 Sep: 19 lion frames across three
# visits, 5 barn owl, 4 jackal, 1 unresolved mammal, and the hare. 29 of the 30
# pass; the hare does not. The other standing miss is still the 30 Aug drinking
# jackal at dom 0.36.
#
# The night set is now dominated by ONE ANIMAL ON ONE NIGHT. Nineteen of the
# fifty rows are the same lion, so this number is a weaker independence claim
# than its size suggests. Read it as "the lion sequence must not break", not as
# fifty independent tests.
REAL_MIN = {("nossob", "night"): 48, ("nossob", "day"): 2}

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
        # 31 Aug - 1 Sep: a second full night, 8 hits in 467 frames, all eight
        # archived and looked at. Every one is an out-of-focus insect or moth
        # on or near the dome. They are big, bright and COMPACT (aspect 1.1 to
        # 1.6), so neither the aspect ceiling nor bpk touches them. Talamati
        # still has no confirmed night animal.
        ("lens insect 31 18:07:00Z p7", M(203, 19, 15, 0.71, 0.85, 5.3, 11)),
        ("lens insect 31 18:59:49Z p7", M(190, 17, 16, 0.70, 0.73, 5.5, 10)),
        ("lens insect 31 19:00:13Z p7", M(156, 16, 14, 0.70, 0.93, 3.6, 8)),
        ("lens insect 31 19:12:54Z p10", M(246, 22, 18, 0.62, 0.95, 5.8, 2)),
        ("lens insect 31 19:13:53Z p12", M(272, 21, 19, 0.68, 1.00, 4.8, 2)),
        ("lens insect 31 19:14:05Z p12", M(212, 19, 16, 0.70, 0.96, 3.6, 4)),
        ("lens insect 31 20:56:10Z p7", M(120, 13, 21, 0.44, 0.77, 3.7, 18)),
        ("lens insect 31 21:37:50Z p10", M(221, 14, 21, 0.75, 1.00, 4.2, 1)),
    ],
    # --- 31 Aug - 1 Sep 2026 Nossob night. The other 68 of that night's 77
    # hits: archived, looked at, nothing in them. By family, roughly 35 swaying
    # grass tufts on the far bank, 10 the floodlit trough rim on preset 14,
    # 10 insects, 5 a bright point in a dark tree preset, 4 the dusk sky and
    # tree of 31 Aug, 2 an unconverged new preset, the rest trough stonework.
    #
    # These are the first bulk confirmed empties the night config has ever had
    # and they are the reason FP_MAX exists below: 57 of them still leak and
    # the job of the next retune is to bring that number down without moving
    # REAL_MIN.
    ("nossob", "night"): [
        ("empty 31 16:19:03Z p24", M(188, 29, 9, 0.72, 0.62, 5.1, 8, 0.057)),
        ("empty 31 16:19:15Z p24", M(99, 22, 6, 0.75, 0.78, 3.6, 6, 0.041)),
        ("empty 31 16:36:07Z p0", M(124, 33, 6, 0.63, 0.76, 5.0, 10, 0.702)),
        ("empty 31 16:49:13Z p8", M(29, 12, 6, 0.40, 0.58, 3.2, 13, 0.405)),
        ("empty 31 16:58:55Z p15", M(11, 4, 4, 0.69, 0.61, 0.8, 6, 0.456)),
        ("empty 31 16:59:08Z p15", M(7, 3, 4, 0.58, 0.47, 0.6, 5, 0.460)),
        ("empty 31 17:02:10Z p11", M(3, 3, 1, 1.00, 0.60, 3.3, 3, 0.667)),
        ("empty 31 17:12:15Z p13", M(6, 2, 4, 0.75, 0.46, 1.5, 6, 0.701)),
        ("empty 31 17:16:03Z p12", M(17, 11, 4, 0.39, 0.55, 1.0, 11, 0.950)),
        ("empty 31 17:27:13Z p8", M(4, 2, 3, 0.67, 0.50, 0.8, 5, 0.968)),
        ("empty 31 17:28:06Z p12", M(6, 4, 3, 0.50, 0.55, 0.6, 4, 0.929)),
        ("empty 31 17:39:18Z p8", M(6, 4, 3, 0.50, 0.86, 0.5, 2, 0.944)),
        ("empty 31 17:42:20Z p8", M(4, 3, 2, 0.67, 0.57, 0.4, 3, 0.319)),
        ("empty 31 17:53:54Z p8", M(3, 2, 2, 0.75, 0.75, 0.5, 2, 0.975)),
        ("empty 31 18:05:10Z p13", M(6, 3, 4, 0.50, 0.67, 0.6, 3, 0.707)),
        ("empty 31 18:17:58Z p15", M(6, 4, 3, 0.50, 0.55, 0.5, 5, 0.904)),
        ("empty 31 18:48:17Z p14", M(3, 2, 2, 0.75, 1.00, 0.4, 1, 0.938)),
        ("empty 31 18:57:57Z p13", M(7, 2, 5, 0.70, 0.58, 0.6, 3, 0.701)),
        ("empty 31 18:58:09Z p8", M(4, 3, 2, 0.67, 0.57, 1.0, 3, 0.977)),
        ("empty 31 19:01:19Z p8", M(4, 2, 3, 0.67, 0.67, 0.6, 3, 0.968)),
        ("empty 31 19:24:13Z p13", M(3, 1, 3, 1.00, 0.50, 0.6, 3, 0.685)),
        ("empty 31 19:27:10Z p13", M(3, 2, 3, 0.50, 1.00, 0.5, 1, 0.704)),
        ("empty 31 19:36:35Z p8", M(3, 1, 3, 1.00, 0.75, 0.5, 2, 0.963)),
        ("empty 31 19:39:00Z p13", M(13, 6, 5, 0.43, 0.62, 0.6, 6, 0.707)),
        ("empty 31 19:39:12Z p8", M(3, 2, 3, 0.50, 0.75, 0.4, 2, 0.963)),
        ("empty 31 19:40:13Z p15", M(3, 2, 2, 0.75, 0.60, 0.5, 3, 0.432)),
        ("empty 31 19:51:55Z p15", M(4, 3, 3, 0.44, 0.80, 0.4, 2, 0.421)),
        ("empty 31 20:04:00Z p11", M(5, 3, 3, 0.56, 0.62, 0.3, 3, 0.019)),
        ("empty 31 20:05:11Z p13", M(3, 2, 3, 0.50, 0.60, 1.0, 3, 0.685)),
        ("empty 31 20:06:57Z p11", M(3, 2, 2, 0.75, 0.60, 0.4, 2, 0.012)),
        ("empty 31 20:30:00Z p15", M(3, 2, 2, 0.75, 0.60, 0.3, 3, 0.957)),
        ("empty 31 20:32:01Z p8", M(3, 2, 3, 0.50, 0.50, 0.3, 4, 0.963)),
        ("empty 31 20:33:15Z p11", M(3, 2, 2, 0.75, 0.75, 0.5, 2, 0.012)),
        ("empty 31 20:44:51Z p11", M(6, 2, 4, 0.75, 0.75, 0.5, 3, 0.441)),
        ("empty 31 20:45:03Z p11", M(5, 2, 4, 0.62, 1.00, 0.3, 1, 0.437)),
        ("empty 31 20:57:07Z p14", M(17, 10, 2, 0.85, 0.50, 1.4, 4, 0.563)),
        ("empty 31 20:59:09Z p15", M(4, 4, 2, 0.50, 0.80, 0.5, 2, 0.449)),
        ("empty 31 21:09:52Z p8", M(4, 2, 3, 0.67, 0.57, 0.4, 4, 0.968)),
        ("empty 31 21:11:15Z p11", M(4, 2, 3, 0.67, 1.00, 0.6, 1, 0.431)),
        ("empty 31 21:12:13Z p16", M(64, 18, 6, 0.59, 0.48, 3.8, 21, 0.449)),
        ("empty 31 21:21:57Z p12", M(8, 4, 5, 0.40, 0.62, 0.9, 3, 0.928)),
        ("empty 31 21:22:56Z p11", M(3, 2, 2, 0.75, 0.60, 0.4, 2, 0.438)),
        ("empty 31 21:37:58Z p14", M(130, 52, 4, 0.62, 0.86, 4.0, 10, 0.568)),
        ("empty 31 21:49:50Z p14", M(9, 6, 2, 0.75, 0.56, 0.9, 5, 0.568)),
        ("empty 31 22:17:03Z p13", M(14, 8, 3, 0.58, 0.64, 2.3, 4, 0.429)),
        ("empty 31 22:28:06Z p14", M(20, 13, 2, 0.77, 0.49, 1.2, 3, 0.562)),
        ("empty 31 22:28:18Z p14", M(14, 10, 2, 0.70, 0.58, 0.8, 2, 0.562)),
        ("empty 31 23:10:52Z p15", M(7, 3, 3, 0.78, 0.58, 2.7, 4, 0.870)),
        ("empty 31 23:34:07Z p15", M(5, 3, 2, 0.83, 0.62, 2.4, 4, 0.878)),
        ("empty 31 23:36:57Z p12", M(4, 2, 3, 0.67, 1.00, 1.0, 1, 0.931)),
        ("empty 31 23:59:07Z p16", M(52, 15, 6, 0.58, 0.71, 2.9, 9, 0.449)),
        ("empty 01 01:10:13Z p8", M(6, 6, 2, 0.50, 0.55, 1.1, 6, 0.441)),
        ("empty 01 01:12:02Z p14", M(5, 3, 3, 0.56, 0.71, 1.0, 2, 0.578)),
        ("empty 01 01:42:11Z p13", M(17, 6, 6, 0.47, 0.59, 1.1, 11, 0.710)),
        ("empty 01 01:43:59Z p11", M(3, 3, 3, 0.33, 0.75, 0.6, 2, 0.222)),
        ("empty 01 01:44:23Z p14", M(24, 15, 2, 0.80, 0.49, 2.1, 4, 0.566)),
        ("empty 01 01:55:32Z p15", M(3, 2, 2, 0.75, 1.00, 0.6, 1, 0.914)),
        ("empty 01 02:16:17Z p11", M(3, 3, 3, 0.33, 1.00, 0.4, 1, 0.222)),
        ("empty 01 02:16:52Z p14", M(6, 4, 3, 0.50, 1.00, 0.5, 1, 0.534)),
        ("empty 01 02:17:15Z p13", M(3, 2, 2, 0.75, 0.60, 1.0, 3, 0.747)),
        ("empty 01 02:32:53Z p12", M(10, 5, 5, 0.40, 0.50, 0.6, 6, 0.950)),
        ("empty 01 02:34:17Z p14", M(6, 4, 3, 0.50, 0.86, 0.6, 2, 0.534)),
        ("empty 01 02:48:56Z p14", M(3, 2, 2, 0.75, 1.00, 0.8, 1, 0.525)),
        ("empty 01 03:01:12Z p13", M(5, 3, 4, 0.42, 0.83, 1.2, 2, 0.693)),
        ("empty 01 03:24:17Z p14", M(32, 15, 3, 0.71, 0.70, 2.5, 5, 0.572)),
        ("empty 01 03:25:18Z p8", M(3, 1, 3, 1.00, 0.60, 0.5, 3, 0.963)),
        ("empty 01 03:39:26Z p14", M(23, 12, 3, 0.64, 0.85, 2.1, 2, 0.572)),
        ("empty 01 03:42:02Z p14", M(5, 5, 1, 1.00, 0.71, 1.2, 3, 0.574)),

        # --- NIGHT OF 1/2 SEP 2026, added 2 Sep. THIRTEEN of that night's
        # confirmed empties, not all 58. Only these thirteen are named
        # individually and described by eye in the handover notes; the other
        # 45 are a count, not a list, and five of the night's 36 animal hits
        # are likewise counted but never written down in animals.md. Until
        # those five are identified, adding the remaining hits in bulk would
        # label up to five animals as false positives. See the notes.
        #
        # FOUR EMPTY p13 FRAMES ON THE LION'S OWN BOX. Seventy minutes after
        # the lion drank there (02 01:40:00, blob 156, 23x11, cx 0.091,
        # cy 0.323, bact 0.064) these fire on an almost identical box with
        # nothing in the frame. Geometry cannot separate them from the lion.
        # bact does: 0.252 to 0.392 against the lion's 0.064.
        ("empty p13, the lion's box, 02 02:53:16Z", M(130, 21, 11, 0.56, 1.00, 2.1, 1, 0.316, 0.252, 0.00)),
        ("empty p13, the lion's box, 02 02:56:17Z", M(106, 19, 11, 0.51, 0.99, 1.5, 2, 0.307, 0.305, 0.00)),
        ("empty p13, the lion's box, 02 02:58:56Z", M(72, 18, 10, 0.40, 0.96, 1.2, 4, 0.300, 0.350, 0.00)),
        ("empty p13, the lion's box, 02 02:59:08Z", M(25, 9, 4, 0.69, 0.83, 0.9, 4, 0.307, 0.392, 0.00)),
        # NINE FLOODLIT INSECTS, every hit of the night with bsat >= 0.25.
        # Eight are on preset 14, blobs of 2x2 to 5x4 at bpk 255. These are
        # what SAT_MAX 0.25 exists for, and it kills them cleanly. Note that
        # bact does NOT catch most of them: only two exceed 0.21.
        ("floodlit insect, 01 18:24:03Z p11", M(3, 3, 3, 0.33, 0.60, 1.1, 2, 0.222, 0.314, 0.33)),
        ("floodlit insect, 01 21:41:51Z p14", M(4, 2, 3, 0.67, 0.50, 0.8, 3, 0.111, 0.142, 0.75)),
        ("floodlit insect, 01 21:42:03Z p14", M(3, 2, 2, 0.75, 1.00, 0.6, 1, 0.105, 0.185, 1.00)),
        ("floodlit insect, 01 21:42:14Z p14", M(3, 2, 2, 0.75, 1.00, 0.5, 1, 0.105, 0.234, 1.00)),
        ("floodlit insect, 01 21:51:08Z p14", M(3, 2, 2, 0.75, 0.50, 0.4, 2, 0.062, 0.098, 0.67)),
        ("floodlit insect, 01 21:53:53Z p14", M(4, 3, 2, 0.67, 0.67, 0.4, 2, 0.046, 0.115, 0.50)),
        ("floodlit insect, 01 21:56:51Z p14", M(6, 3, 3, 0.67, 0.75, 0.5, 2, 0.037, 0.132, 0.67)),
        ("floodlit insect, 01 21:57:02Z p14", M(6, 3, 3, 0.67, 1.00, 0.3, 1, 0.037, 0.184, 0.67)),
        ("floodlit insect, 02 00:05:55Z p14", M(12, 5, 4, 0.60, 1.00, 1.2, 1, 0.755, 0.060, 1.00)),
    ],
}

# Confirmed-empty frames we currently still leak. A ceiling, not a target: the
# test fails if the count RISES. Nossob night is 36 of 68 as of the evening of
# 1 Sep 2026: 68 before FILL_WIDE went to 1.01, 57 after it, 36 after CY_MAX
# 0.85. Both of those changes cost nothing on the 17 confirmed animals, so the
# detection line above did not move. Night precision on the 31 Aug - 1 Sep log
# goes 9 of 77 -> 9 of 66 -> 9 of 45, about 20%.
# Talamati night is 8 of 21: the 13 rows of 30-31 Aug are all rejected, but the
# eight lens insects of 1 Sep all get through and nothing in cameras.py can
# stop them. They are big, compact and bright, which is also what a genuine
# large animal at that waterhole would be. Fixing this needs the corrected
# `bsat`, not a threshold.
#
# NOSSOB NIGHT IS NOW 43 OF 81, revised 2 Sep 2026 evening. The denominator
# grew from 68 to 81 with the thirteen named empties of 1/2 Sep. The path:
#   81 rows, BACT_MAX inert (the config deployed on 1 Sep)  49 leak
#   + BACT_MAX 0.21                                         43 leak
# Recall did not move: 48 of 50 both before and after. Nothing is traded.
#
# SAT_MAX 0.25 was MEASURED AND NOT SHIPPED. On top of BACT_MAX it takes this
# to 36 of 81, still at 48 of 50. It is held back so the next night is a clean
# out-of-sample test of BACT_MAX alone. If it is added later, drop this to 36.
#
# CAUTION ON THE DENOMINATOR. 81 is not the whole picture. The night of 1/2 Sep
# produced 58 confirmed empties and only 13 of them are named individually
# anywhere, so 45 real false positives are absent from this file. Measured on
# the full archive instead of on this set, BACT_MAX 0.21 removes 17 of those
# 58, not 6 of 13. Neither number is wrong; they are different denominators.
FP_MAX = {("nossob", "day"): 0, ("nossob", "night"): 43, ("talamati", "night"): 8}

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

    print("\nCONFIRMED animals in real frames (30 Aug - 2 Sep 2026)")
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

    print("\nCONFIRMED empty in real frames: leaks must not exceed FP_MAX")
    for (cam, mode), rows in CONFIRMED_FP.items():
        leaks = [l for l, m in rows if is_hit(m, BIG_N, thr_for(cam, mode))]
        cap = FP_MAX[(cam, mode)]
        ok = len(leaks) <= cap
        bad += 0 if ok else len(leaks) - cap
        print(f"  {'ok  ' if ok else 'FAIL'} {cam:9s} {mode:5s} "
              f"{len(leaks)}/{len(rows)} leaked (cap {cap})")
        if not ok:
            for l in leaks:
                print(f"         leaked: {l}")

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
