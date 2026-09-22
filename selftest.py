#!/usr/bin/env python3
"""
Regression test for the decision rule.

Every row below is a real measurement, not a guess:

  NATURAL  - the largest blob found in a real frame with no animal in it.
             Any of these that scores a hit is a false positive.
  INJECTED - the same pipeline run on a real frame and its real learned
             background with a synthetic elliptical target added, so the
             geometry is what the detector would actually see.

             SCORED TWICE since 3 Sep 2026. In GEOMETRY mode at dist 0 and
             nblobs 1, which is what the shape alone can do, and in FIELD mode
             at the camera's real daylight dist and nblobs, which is what the
             detector would actually do. The old suite reported only the first
             and so read 8/8 while the live detector caught nothing in daylight
             for four days. See the FIELD block for the numbers and their
             provenance.

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

# NATURAL used to assert zero leaks everywhere, with no way to say "this leak
# is the measured price of a change we took on purpose". ADDED 4 SEP 2026
# EVENING, because the Kruger daylight bundle leaks two of the thirteen
# Talamati daylight naturals and a suite that simply goes red says nothing
# about whether that was two or twelve.
#
# THE RULE FOR THIS DICT IS THE SAME AS FOR FP_MAX. A cap is a measurement
# written down, never a way to make a failure go away. Raise it only with the
# leaked rows named and the reason stated, and never raise it in the same
# session as the change that caused the leak without saying so out loud.
#
# talamati day 2: FILL_CMP 0.44 -> 0.26 leaks blob 147 (24x16, fill 0.38) and
# blob 101 (22x16, fill 0.29). Both are real Talamati daylight frames with no
# animal in them, measured 30 Aug 2026 13:39-14:07 UTC. They are exactly the
# frames the Talamati elephant of 03 10:22:08 cannot be separated from: it
# needs fill 0.28 and the nearest empty sits at 0.29. There is no gap and no
# value of FILL_CMP that takes one and not the other.
#
# EVERYTHING ELSE IS 0 AND MUST STAY 0.
# RAISED 2 -> 9 ON 7 SEP 2026, deliberately, with FILL_WIDE 0.72 -> 0.30 at
# Kruger daylight. This is the whole price of that change inside this harness
# and it is recorded rather than hidden.
#
# WHY THE LEAK IS ACCEPTED. This set is 13 frames. On 7 Sep Jeremy reviewed the
# entire archive by eye, which yields 1,153 eye-confirmed EMPTY Kruger daylight
# frames against 37 eye-confirmed MAMMAL frames. Measured on those: FILL_WIDE
# 0.72 catches 12 of 37 mammals and leaks 347 of 1,153 empties; 0.30 catches 19
# of 37 and leaks 499. Seven more leaks in a 13-frame synthetic set is the same
# trade seen at 90x the sample size, and there it is worth taking.
#
# THE 4 SEP DECISION IS SUPERSEDED, NOT FORGOTTEN. FILL_WIDE 0.26 was rejected
# that evening precisely because it took this number from 2 to 9. The reason it
# is now accepted is that a real negative set exists and a real mammal set
# exists; neither did on 4 September.
#
# EVERYTHING ELSE IS 0 AND MUST STAY 0.
NATURAL_CAP = {("talamati", "day"): 9}

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

        # --- NIGHT OF 2/3 SEP 2026, added 3 Sep evening. Three frames from
        # frames/nossob/20260902, each looked at with the logged cx/cy/bw/bh
        # box drawn on it, each box landing on the animal. A fourth frame of
        # that night, 03 02:08:58 p15 blob 10, contains an animal and is NOT
        # here: its box is on the trough rim while the animal is up in the
        # grass at the top left. It is in animals.md as seen but not measured.
        #
        # THE LION FRAME IS THE ONE THAT MOVED A THRESHOLD. At dist 7.2 it was
        # a single-gate miss under DIST_MAX 6.0, and it is the whole reason
        # Nossob night DIST_MAX is now 8.0. Keep it here: if DIST_MAX is ever
        # taken back below 7.2 this row is what fails.
        ("jackal at the rim, side on, 02 17:44:17Z", M(66, 11, 12, 0.50, 0.94, 1.2, 4, 0.399, 0.064, 0.00)),
        ("THREE LIONS drinking, 02 21:16:00Z", M(252, 17, 27, 0.55, 0.49, 7.2, 7, 0.254, 0.063, 0.00)),
        ("LIONS drinking, left of the pan, 02 23:02:59Z", M(201, 28, 19, 0.38, 0.99, 2.1, 3, 0.311, 0.063, 0.00)),
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
#
# NIGHT 51 OF 53 as of 3 Sep 2026 evening, up from 48 of 50. Three rows added
# from the night of 2/3 Sep, all three caught: a jackal at the rim, and two
# separate lion groups. The two standing misses are unchanged (the 30 Aug
# drinking jackal at dom 0.36, and the hare).
#
# 51 IS A GUARD ON DIST_MAX, NOT JUST A COUNT. The 02 21:16:00 lion row sits
# at dist 7.2 and only passes because Nossob night DIST_MAX went to 8.0 in the
# same session. Take DIST_MAX back below 7.2 and this drops to 50 and FAILS.
# That is deliberate: the threshold and the animal that justifies it are now
# tied together in the test.
# --- SATARA DAYLIGHT: THE FIRST KRUGER DAYLIGHT REAL_ANIMAL ROWS -------------
# ADDED 4 SEP 2026 EVENING. Until tonight this harness had NO Kruger daylight
# REAL_ANIMAL row at all, which was measured the same day by sweeping NB_MAX at
# both Kruger cameras from 25 to 200 and watching every detection and leak
# count stay identical at every value. It could reject a Kruger daylight change
# and it could not reward one, so it would have certified the 4 Sep evening
# bundle blind.
#
# ALL THREE ROWS ARE SECTION A: the logged blob box is demonstrably on the
# animal, checked by eye with the box drawn on the 900x506 archived JPEG. Rows
# where the box lands elsewhere stay in KNOWN_MISSES and vote on nothing.
#
# ALL THREE WERE MISSED BY THE CONFIG OF THIS MORNING, on NB_MAX 25 at nblobs
# 217, 200 and 189. If a future edit takes this count below 3, it has closed
# NB_MAX or FILL_CMP back down and it should say so.
REAL_ANIMAL[("satara", "day")] = [
    # Single dark glossy thrush-sized bird at the near rim with its reflection
    # as one connected region; scale reference is the channel width. THE
    # HIGHEST nblobs OF ANY CONFIRMED ANIMAL ANYWHERE, 217, which is why
    # NB_MAX is 250 and not 200. bact 0.43 against a Satara daylight
    # population median of about 0.28: a confirmed animal standing at the
    # water is MORE restless than the average frame, which is why no daylight
    # bact or ACT_MAX gate can ever be used at this camera.
    ("04 06:49:01Z p12, glossy bird + reflection at the rim, BOX ON IT",
     M(116, 20, 21, 0.28, 0.09, 3.2, 217, 0.0, 0.43, 0.0)),
    # Group of 8-10 small birds on the left rim, box on the group.
    ("04 06:21:10Z p23, 8-10 small birds on the rim, BOX ON THEM",
     M(112, 21, 14, 0.38, 0.15, 4.5, 200, 0.0, 0.212, 0.0)),
    # PROMOTED OUT OF KNOWN_MISSES 4 SEP 2026 EVENING under the promotion rule
    # at the head of that dict: it is detected by the live config, so it is a
    # floor worth guarding. Spotted hyena, adult standing in the channel with
    # two juveniles; the box covers the adult plus a lot of channel.
    ("03 09:53:04Z p6, 3 spotted hyenas, BOX ON THE ADULT",
     M(239, 44, 20, 0.27, 0.21, 3.6, 189, 0.299, 0.261, 0.08)),
]

# --- TALAMATI DAYLIGHT: THE ONLY ROW THIS CAMERA HAS THAT MEASURES AN ANIMAL
# ADDED 4 SEP 2026 LATE EVENING, promoted out of KNOWN_MISSES.
#
# Four elephants at the reservoir wall including a calf. The box covers the
# drinking adult, the calf and the walking animal; it is not tight, it contains
# wall as well as elephant, but it is on the animals. blob 242 clears BLOB_MIN
# 60 four times over and n=36 is well past MIN_N, so this is a field detection
# and not a harness artefact.
#
# IT IS A THREE-GATE RECOVERY AND ALL THREE ARE LOAD-BEARING ON IT. dist 7.6
# needs DIST_MAX 8.0, nblobs 38 needs NB_MAX above 38, fill 0.28 needs FILL_CMP
# below 0.28. Close any one of the three and this drops to 0/1 and the suite
# goes red. That is deliberate: the threshold and the animal that justifies it
# are tied together in the test.
REAL_ANIMAL[("talamati", "day")] = [
    ("03 10:22:08Z p90, 4 elephants at the wall, BOX ON THEM",
     M(242, 34, 25, 0.28, 0.60, 7.6, 38, 0.568, 0.356, 0.13)),
]

# satara night 3, ADDED 21 SEP 2026 with BLOB_MIN 90 -> 50 at Satara night.
# SATARA'S FIRST NIGHT POSITIVES. Before today this file had no Satara night
# animal at all, so it priced BLOB_MIN nothing: under 50 every verdict was
# identical to 90. From the Satara review pass of 8 to 18 Sep 2026, rows copied
# from logs/satara/ by the tarball of 22 Sep, not typed. Each box was drawn
# with tools/draw_boxes.py and is on the animal.
#   17:06:52 fires at 90 and 50. The box reaches the water line, so part of
#            the blob may be reflection.
#   20:49:54 and 21:35:11 fire at 50 only. 0/3 -> 1/3 -> 3/3 is the whole
#   argument for the change, and 21:35:11 at blob 51 is the thin margin.
REAL_ANIMAL[("satara", "night")] = [
    ("14 17:06:52Z p3, drinking at the edge, BOX ON IT",
     M(102, 20, 13, 0.39, 0.85, 1.9, 7, 0.286, 0.061, 0.0)),
    ("14 20:49:54Z p31, sitting on the bank, BOX ON IT",
     M(72, 16, 12, 0.38, 0.81, 2.1, 4, 0.614, 0.061, 0.0)),
    ("14 21:35:11Z p23, walking the bank at the left edge, BOX ON IT",
     M(51, 12, 6, 0.71, 0.86, 1.8, 3, 0.625, 0.08, 0.0)),
]

# satara day 3 ADDED 4 SEP 2026 EVENING, and it is a hard floor: all three rows
# pass under the bundle and all three failed before it. 0/3 before, 3/3 after.
#
# talamati day 1 ADDED 4 SEP 2026 LATE EVENING with DIST_MAX 8.0. 0/1 before
# tonight, 1/1 after. It is the first Talamati recall floor of any kind, in
# either mode, that this file has ever carried.
#
# nossob day 2 -> 3 ON 20 SEP 2026 with NB_MAX 250 and FILL_CMP 0.30. The row
# that moves is the BATELEUR at the pan, 01 13:52:18Z: nblobs above 25 was the
# first gate it failed. The wider-preset bateleur of 01 13:55:14Z and the blue
# wildebeest pair of 01 12:59:04Z still miss, so this is 3 of 5 and not 5 of 5.
# It is the first time this camera's daylight recall floor has moved.
#
# satara night 3 ADDED 21 SEP 2026. Under BLOB_MIN 90 this row set scores
# 1/3; the floor is written at the new value and ties BLOB_MIN 50 to the two
# rows that justify it.
REAL_MIN = {("nossob", "night"): 51, ("nossob", "day"): 3,
            ("satara", "day"): 3, ("talamati", "day"): 1,
            ("satara", "night"): 3}

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
        # --- ADDED 4 SEP 2026: FOUR TALAMATI p41 FRAMES, ALL REVIEWED --------
        # The first two are the RESERVOIR WALL view and differ from each other
        # only by a whole-frame haze and gain shift. The second two are the
        # GRASS view of the SAME PRESET ID (see cameras.py on p41: preset 41 is
        # two camera positions) and each contains a small dark mark low in the
        # grass at the IDENTICAL pixel position 29 minutes apart, which is a
        # static gap in a tussock, not an animal.
        #
        # These are the most useful negatives in this file today, because they
        # sit on the preset the 4 Sep SIG_TOL change is aimed at. If splitting
        # p41 turns any of them into a leak, this suite says so immediately.
        ("talamati p41 03 18:27:52Z wall, gain shift", M(626, 70, 19, 0.47, 0.53, 18.1, 67, 0.833, 0.351, 0.34)),
        ("talamati p41 03 18:28:05Z wall, gain shift", M(291, 38, 18, 0.43, 0.43, 12.1, 52, 0.834, 0.453, 0.19)),
        ("talamati p41 03 18:33:05Z grass, static gap", M(621, 52, 38, 0.31, 0.44, 18.3, 55, 0.406, 0.360, 0.30)),
        ("talamati p41 03 19:02:14Z grass, same gap 29 min later", M(385, 55, 19, 0.37, 0.33, 17.0, 53, 0.800, 0.350, 0.28)),
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
    # --- ADDED 4 SEP 2026: SATARA'S FIRST NEGATIVE ROW -------------------------
    # 04 02:25:12 p4, reviewed with the box drawn. px 12,930 and nblobs 107 on a
    # hazy flat frame with nothing in it. It sits 22 minutes after the confirmed
    # spotted hyena on the same preset, which is why it was pulled and looked at.
    ("satara", "night"): [
        ("satara 04 02:25:12Z p4, haze", M(154, 44, 12, 0.29, 0.16, 5.1, 107, 0.892, 0.171, 0.00)),
        # ADDED 21 SEP 2026: ALL 180 EYE-CONFIRMED SATARA NIGHT EMPTIES of the
        # review pass of 8 to 18 Sep 2026 (keys in tools/reviewed.txt and not in
        # tools/ground_truth.txt, night mode), rows copied mechanically from
        # logs/satara/ by UTC second. Scored here at BIG_N, so MIN_N never
        # votes; replayed with the real n the leak count is the same.
        ("satara 08 23:53:17Z p4", M(1, 1, 1, 1.0, 0.5, 0.4, 2, 0.685, 0.08, 0.0)),
        ("satara 09 01:27:58Z p4", M(1, 1, 1, 1.0, 1.0, 0.5, 1, 0.87, 0.164, 0.0)),
        ("satara 09 02:21:36Z p4", M(1, 1, 1, 1.0, 0.25, 0.4, 4, 0.648, 0.211, 0.0)),
        ("satara 09 16:00:13Z p35", M(680, 86, 30, 0.26, 0.73, 8.8, 93, 0.445, 0.156, 0.0)),
        ("satara 09 19:50:36Z p4", M(24, 6, 9, 0.44, 0.56, 0.7, 10, 0.123, 0.064, 0.0)),
        ("satara 09 20:21:01Z p4", M(1, 1, 1, 1.0, 1.0, 0.6, 1, 0.815, 0.107, 0.0)),
        ("satara 10 23:04:23Z p43", M(5, 3, 3, 0.56, 0.38, 2.9, 6, 0.185, 0.159, 0.0)),
        ("satara 11 01:47:14Z p4", M(2, 1, 2, 1.0, 1.0, 0.7, 1, 0.917, 0.06, 0.0)),
        ("satara 11 01:55:00Z p43", M(10, 8, 3, 0.42, 0.15, 3.5, 25, 0.096, 0.19, 0.0)),
        ("satara 11 03:41:55Z p71", M(689, 89, 29, 0.27, 0.76, 8.0, 105, 0.445, 0.333, 0.0)),
        ("satara 11 16:09:08Z p4", M(197, 32, 21, 0.29, 0.18, 7.7, 106, 0.296, 0.061, 0.0)),
        ("satara 11 16:24:57Z p4", M(72, 20, 7, 0.51, 0.13, 6.2, 120, 0.473, 0.116, 0.0)),
        ("satara 11 18:25:15Z p4, LEAKS AT 50", M(122, 24, 13, 0.39, 0.54, 1.1, 19, 0.806, 0.112, 0.0)),
        ("satara 11 20:01:09Z p31", M(2, 2, 1, 1.0, 0.67, 0.4, 2, 0.389, 0.334, 0.0)),
        ("satara 11 20:53:56Z p31", M(5, 5, 1, 1.0, 0.83, 0.6, 2, 0.389, 0.258, 0.0)),
        ("satara 12 03:35:56Z p153", M(1805, 96, 54, 0.35, 0.88, 5.9, 84, 0.495, 0.303, 0.0)),
        ("satara 12 16:31:03Z p5", M(37, 17, 8, 0.27, 0.27, 3.9, 34, 0.446, 0.147, 0.0)),
        ("satara 12 17:08:17Z p4", M(360, 47, 20, 0.38, 0.27, 7.3, 105, 0.808, 0.077, 0.0)),
        ("satara 12 18:04:54Z p44", M(330, 51, 24, 0.27, 0.28, 5.6, 118, 0.78, 0.299, 0.0)),
        ("satara 12 20:40:57Z p5", M(18, 8, 3, 0.75, 0.72, 5.4, 3, 0.447, 0.164, 0.06)),
        ("satara 13 03:01:03Z p64", M(203, 34, 18, 0.33, 0.57, 1.6, 44, 0.508, 0.446, 0.0)),
        ("satara 13 03:42:51Z p27", M(403, 54, 13, 0.57, 0.4, 10.6, 38, 0.478, 0.113, 0.0)),
        ("satara 13 03:58:12Z p26", M(74, 21, 6, 0.59, 0.94, 4.8, 3, 0.844, 0.174, 0.0)),
        ("satara 13 17:20:00Z p67", M(176, 81, 15, 0.14, 0.38, 5.3, 20, 0.233, 0.238, 0.0)),
        ("satara 13 20:57:25Z p89", M(515, 64, 17, 0.47, 0.88, 6.2, 9, 0.744, 0.134, 0.04)),
        ("satara 13 21:19:12Z p37", M(117, 68, 14, 0.12, 0.29, 5.6, 33, 0.197, 0.378, 0.0)),
        ("satara 14 23:17:57Z p4", M(22, 6, 8, 0.46, 0.2, 0.5, 26, 0.654, 0.086, 0.0)),
        ("satara 15 01:49:57Z p4", M(22, 6, 5, 0.73, 0.96, 1.1, 2, 0.263, 0.061, 0.27)),
        ("satara 15 03:44:32Z p71", M(337, 47, 23, 0.31, 0.49, 9.1, 128, 0.481, 0.171, 0.0)),
        ("satara 17 00:07:38Z p4", M(46, 11, 12, 0.35, 0.28, 1.3, 38, 0.792, 0.351, 0.0)),
        ("satara 17 00:38:04Z p5", M(442, 94, 29, 0.16, 0.45, 6.4, 113, 0.404, 0.081, 0.0)),
        ("satara 17 01:04:44Z p4", M(99, 17, 13, 0.45, 0.52, 1.6, 47, 0.796, 0.304, 0.0)),
        ("satara 17 01:19:39Z p4", M(54, 13, 16, 0.26, 0.24, 1.5, 41, 0.757, 0.248, 0.0)),
        ("satara 17 01:31:47Z p39", M(311, 54, 16, 0.36, 0.89, 6.0, 12, 0.723, 0.335, 0.0)),
        ("satara 17 01:50:22Z p23", M(42, 17, 5, 0.49, 0.88, 1.4, 5, 0.463, 0.108, 0.0)),
        ("satara 17 02:05:50Z p64", M(84, 29, 14, 0.21, 0.23, 7.1, 65, 0.437, 0.408, 0.0)),
        ("satara 17 02:30:47Z p38", M(179, 29, 16, 0.39, 0.27, 7.5, 88, 0.738, 0.273, 0.0)),
        ("satara 17 02:42:56Z p4", M(24, 4, 12, 0.5, 0.2, 1.1, 41, 0.174, 0.311, 0.0)),
        ("satara 17 02:58:22Z p33", M(373, 90, 22, 0.19, 0.38, 6.7, 112, 0.236, 0.183, 0.0)),
        ("satara 17 03:23:11Z p91", M(562, 53, 29, 0.37, 0.86, 8.9, 27, 0.681, 0.186, 0.0)),
        ("satara 17 03:39:10Z p12", M(623, 63, 33, 0.3, 0.4, 6.0, 149, 0.596, 0.183, 0.0)),
        ("satara 17 16:14:49Z p4", M(236, 36, 16, 0.41, 0.34, 5.2, 97, 0.845, 0.153, 0.0)),
        ("satara 17 16:26:04Z p3", M(33, 9, 7, 0.52, 0.3, 2.3, 22, 0.668, 0.116, 0.0)),
        ("satara 17 16:26:52Z p4", M(68, 19, 8, 0.45, 0.19, 3.3, 94, 0.903, 0.155, 0.0)),
        ("satara 17 16:27:04Z p31", M(20, 11, 3, 0.61, 0.28, 1.2, 16, 0.384, 0.083, 0.0)),
        ("satara 17 16:27:51Z p2", M(10, 6, 3, 0.56, 0.3, 2.4, 9, 0.787, 0.066, 0.0)),
        ("satara 17 16:28:03Z p2", M(6, 4, 3, 0.5, 0.27, 1.8, 6, 0.793, 0.144, 0.0)),
        ("satara 17 16:41:48Z p4", M(76, 17, 12, 0.37, 0.36, 2.4, 49, 0.789, 0.317, 0.0)),
        ("satara 17 16:54:29Z p31", M(20, 11, 3, 0.61, 0.36, 1.0, 18, 0.415, 0.07, 0.0)),
        ("satara 17 17:17:00Z p31", M(21, 11, 3, 0.64, 0.68, 0.5, 6, 0.414, 0.181, 0.0)),
        ("satara 17 17:23:04Z p4", M(203, 33, 17, 0.36, 0.6, 1.6, 45, 0.774, 0.215, 0.0)),
        ("satara 17 17:38:05Z p4", M(25, 4, 15, 0.42, 0.35, 4.1, 31, 0.124, 0.27, 0.0)),
        ("satara 17 18:03:07Z p125", M(321, 54, 19, 0.31, 0.86, 2.1, 25, 0.673, 0.33, 0.11)),
        ("satara 17 18:07:56Z p3", M(22, 9, 6, 0.41, 0.58, 0.4, 10, 0.635, 0.073, 0.0)),
        ("satara 17 18:31:01Z p3", M(3, 2, 3, 0.5, 0.43, 0.6, 4, 0.759, 0.097, 0.0)),
        ("satara 17 18:50:25Z p44", M(160, 26, 27, 0.23, 0.15, 6.4, 116, 0.686, 0.243, 0.0)),
        ("satara 17 19:05:56Z p4", M(66, 18, 13, 0.28, 0.36, 0.7, 38, 0.819, 0.258, 0.0)),
        ("satara 17 19:21:48Z p31", M(8, 6, 4, 0.33, 0.2, 0.4, 18, 0.562, 0.083, 0.0)),
        ("satara 17 19:36:47Z p31", M(36, 12, 8, 0.38, 0.59, 0.8, 13, 0.36, 0.111, 0.0)),
        ("satara 17 19:59:12Z p5", M(141, 39, 9, 0.4, 0.61, 5.0, 24, 0.408, 0.115, 0.0)),
        ("satara 17 20:12:00Z p41", M(109, 33, 11, 0.3, 0.65, 8.5, 23, 0.597, 0.203, 0.05)),
        ("satara 17 20:25:51Z p5", M(367, 56, 15, 0.44, 0.7, 8.0, 35, 0.394, 0.128, 0.0)),
        ("satara 17 20:30:06Z p2, LEAKS AT 50", M(287, 37, 17, 0.46, 0.68, 5.5, 16, 0.745, 0.073, 0.0)),
        ("satara 17 20:30:52Z p30, LEAKS AT 50", M(97, 16, 13, 0.47, 0.49, 5.5, 13, 0.78, 0.065, 0.0)),
        ("satara 17 20:34:15Z p2, LEAKS AT 50", M(133, 15, 16, 0.55, 0.8, 4.1, 7, 0.768, 0.13, 0.02)),
        ("satara 17 20:46:59Z p3", M(36, 5, 11, 0.65, 1.0, 2.9, 1, 0.073, 0.06, 0.0)),
        ("satara 17 21:01:33Z p89", M(436, 64, 20, 0.34, 0.68, 8.0, 38, 0.718, 0.224, 0.0)),
        ("satara 17 21:13:46Z p90", M(116, 31, 8, 0.47, 0.39, 9.9, 49, 0.062, 0.118, 0.0)),
        ("satara 17 21:41:06Z p37", M(160, 40, 14, 0.29, 0.4, 6.8, 21, 0.391, 0.283, 0.0)),
        ("satara 17 21:48:03Z p4", M(24, 6, 10, 0.4, 0.18, 5.4, 40, 0.799, 0.201, 0.0)),
        ("satara 17 22:03:51Z p5", M(368, 44, 20, 0.42, 0.69, 7.3, 44, 0.423, 0.159, 0.0)),
        ("satara 17 22:19:14Z p31", M(37, 8, 8, 0.58, 0.58, 2.1, 13, 0.56, 0.133, 0.0)),
        ("satara 17 22:32:39Z p30, LEAKS AT 50", M(57, 9, 8, 0.79, 0.8, 1.5, 9, 0.577, 0.068, 0.0)),
        ("satara 17 22:53:06Z p5", M(240, 32, 18, 0.42, 0.65, 5.1, 36, 0.401, 0.228, 0.0)),
        ("satara 17 23:02:09Z p30", M(555, 73, 25, 0.3, 0.62, 3.5, 106, 0.802, 0.066, 0.0)),
        ("satara 17 23:16:59Z p2", M(2, 1, 2, 1.0, 0.5, 0.4, 2, 0.731, 0.474, 0.0)),
        ("satara 17 23:45:57Z p4", M(6, 4, 2, 0.75, 0.16, 1.2, 22, 0.975, 0.329, 0.0)),
        ("satara 18 00:04:56Z p33", M(167, 33, 14, 0.36, 0.25, 5.3, 111, 0.753, 0.332, 0.0)),
        ("satara 18 00:26:10Z p91", M(216, 49, 12, 0.37, 0.35, 7.9, 72, 0.909, 0.223, 0.0)),
        ("satara 18 00:43:42Z p31", M(3, 2, 2, 0.75, 0.43, 0.5, 4, 0.284, 0.206, 0.0)),
        ("satara 18 01:04:58Z p4", M(45, 9, 15, 0.33, 0.18, 1.8, 60, 0.711, 0.226, 0.0)),
        ("satara 18 01:41:51Z p36", M(104, 42, 20, 0.12, 0.23, 7.2, 71, 0.519, 0.168, 0.0)),
        ("satara 18 01:50:59Z p33", M(37, 16, 7, 0.33, 0.1, 4.0, 103, 0.205, 0.36, 0.0)),
        ("satara 18 02:06:06Z p5", M(19, 6, 8, 0.4, 0.21, 1.3, 22, 0.12, 0.278, 0.0)),
        ("satara 18 02:25:17Z p31", M(10, 7, 3, 0.48, 0.37, 0.7, 9, 0.428, 0.145, 0.0)),
        ("satara 18 02:50:54Z p4", M(211, 35, 19, 0.32, 0.64, 1.2, 43, 0.753, 0.177, 0.0)),
        ("satara 18 02:55:56Z p31", M(13, 5, 6, 0.43, 0.52, 0.4, 10, 0.328, 0.194, 0.0)),
        ("satara 18 03:13:49Z p4", M(45, 9, 13, 0.38, 0.28, 1.0, 62, 0.752, 0.229, 0.0)),
        ("satara 18 03:31:23Z p30", M(8, 4, 3, 0.67, 0.67, 3.6, 2, 0.56, 0.077, 0.0)),
        ("satara 18 03:54:39Z p185", M(108, 22, 8, 0.61, 0.32, 5.8, 73, 0.054, 0.075, 0.0)),
        ("satara 18 16:18:50Z p38", M(137, 64, 15, 0.14, 0.26, 5.9, 82, 0.396, 0.184, 0.0)),
        ("satara 18 16:41:02Z p4", M(261, 39, 21, 0.32, 0.57, 1.0, 31, 0.762, 0.169, 0.0)),
        ("satara 18 16:46:59Z p41", M(204, 41, 17, 0.29, 0.44, 7.4, 63, 0.629, 0.293, 0.0)),
        ("satara 18 17:04:13Z p4", M(83, 16, 16, 0.32, 0.41, 0.5, 28, 0.723, 0.279, 0.0)),
        ("satara 18 17:27:04Z p5", M(59, 15, 14, 0.28, 0.64, 1.0, 11, 0.178, 0.272, 0.0)),
        ("satara 18 17:33:09Z p91", M(145, 31, 10, 0.47, 0.47, 5.5, 28, 0.8, 0.264, 0.0)),
        ("satara 18 17:33:55Z p38", M(5, 4, 2, 0.62, 0.22, 2.1, 15, 0.659, 0.334, 0.0)),
        ("satara 18 17:34:07Z p4", M(1, 1, 1, 1.0, 0.25, 0.2, 4, 0.593, 0.449, 0.0)),
        ("satara 18 17:35:05Z p31", M(2, 2, 2, 0.5, 0.5, 0.2, 2, 0.306, 0.208, 0.0)),
        ("satara 18 17:35:51Z p2", M(1, 1, 1, 1.0, 1.0, 0.3, 1, 0.741, 0.294, 0.0)),
        ("satara 18 17:36:49Z p30", M(3, 3, 1, 1.0, 1.0, 0.3, 1, 0.537, 0.08, 0.0)),
        ("satara 18 17:37:12Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:37:59Z p4", M(19, 5, 8, 0.47, 0.15, 0.5, 36, 0.746, 0.342, 0.0)),
        ("satara 18 17:38:10Z p4", M(3, 2, 2, 0.75, 0.12, 0.3, 17, 0.735, 0.3, 0.0)),
        ("satara 18 17:38:57Z p31", M(3, 2, 2, 0.75, 0.5, 0.3, 3, 0.29, 0.228, 0.0)),
        ("satara 18 17:39:08Z p31", M(2, 2, 2, 0.5, 0.67, 0.2, 2, 0.287, 0.17, 0.0)),
        ("satara 18 17:39:55Z p2", M(1, 1, 1, 1.0, 0.5, 0.2, 2, 0.722, 0.434, 0.0)),
        ("satara 18 17:40:06Z p30", M(1, 1, 1, 1.0, 0.5, 0.2, 2, 0.537, 0.06, 0.0)),
        ("satara 18 17:40:53Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:41:04Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:41:51Z p4", M(37, 16, 11, 0.21, 0.31, 0.5, 33, 0.761, 0.264, 0.0)),
        ("satara 18 17:42:02Z p4", M(29, 8, 10, 0.36, 0.35, 0.4, 24, 0.752, 0.236, 0.0)),
        ("satara 18 17:42:14Z p4", M(12, 6, 5, 0.4, 0.36, 0.3, 16, 0.753, 0.34, 0.0)),
        ("satara 18 17:44:25Z p30", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:44:48Z p3", M(0, 1, 1, 0.0, 0.0, 0.1, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:45:11Z p3", M(0, 1, 1, 0.0, 0.0, 0.1, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:45:58Z p4", M(160, 31, 14, 0.37, 0.69, 0.5, 30, 0.751, 0.2, 0.0)),
        ("satara 18 17:46:10Z p23", M(34, 16, 4, 0.53, 0.63, 1.0, 9, 0.467, 0.129, 0.0)),
        ("satara 18 17:46:56Z p2", M(2, 2, 1, 1.0, 0.67, 0.3, 2, 0.722, 0.327, 0.0)),
        ("satara 18 17:47:08Z p2", M(1, 1, 1, 1.0, 1.0, 0.2, 1, 0.741, 0.304, 0.0)),
        ("satara 18 17:47:54Z p30", M(1, 1, 1, 1.0, 1.0, 0.2, 1, 0.537, 0.113, 0.0)),
        ("satara 18 17:48:06Z p30", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:48:54Z p3", M(0, 1, 1, 0.0, 0.0, 0.3, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:49:05Z p4", M(8, 5, 5, 0.32, 0.11, 0.4, 34, 0.838, 0.353, 0.0)),
        ("satara 18 17:49:52Z p23", M(31, 16, 4, 0.48, 0.76, 1.1, 7, 0.467, 0.177, 0.0)),
        ("satara 18 17:50:04Z p31", M(2, 1, 2, 1.0, 0.29, 0.2, 5, 0.306, 0.156, 0.0)),
        ("satara 18 17:50:50Z p2", M(3, 2, 2, 0.75, 0.43, 0.1, 3, 0.728, 0.348, 0.0)),
        ("satara 18 17:51:14Z p2", M(1, 1, 1, 1.0, 1.0, 0.1, 1, 0.741, 0.385, 0.0)),
        ("satara 18 17:51:49Z p30", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:52:14Z p3", M(0, 1, 1, 0.0, 0.0, 0.5, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:52:49Z p4", M(45, 13, 11, 0.31, 0.37, 0.4, 28, 0.765, 0.331, 0.0)),
        ("satara 18 17:53:12Z p4", M(31, 9, 8, 0.43, 0.46, 0.4, 21, 0.75, 0.394, 0.0)),
        ("satara 18 17:53:47Z p31", M(3, 3, 2, 0.5, 0.6, 0.2, 2, 0.272, 0.122, 0.0)),
        ("satara 18 17:53:59Z p31", M(1, 1, 1, 1.0, 1.0, 0.1, 1, 0.278, 0.241, 0.0)),
        ("satara 18 17:54:11Z p31", M(4, 3, 2, 0.67, 0.8, 0.1, 2, 0.287, 0.227, 0.0)),
        ("satara 18 17:54:57Z p2", M(2, 2, 1, 1.0, 0.5, 0.2, 2, 0.722, 0.368, 0.0)),
        ("satara 18 17:55:09Z p30", M(0, 1, 1, 0.0, 0.0, 0.9, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:55:56Z p91", M(10, 9, 2, 0.56, 0.36, 4.1, 14, 0.696, 0.26, 0.0)),
        ("satara 18 17:56:08Z p3", M(1, 1, 1, 1.0, 1.0, 0.2, 1, 0.593, 0.077, 0.0)),
        ("satara 18 17:57:48Z p31", M(1, 1, 1, 1.0, 1.0, 0.7, 1, 0.296, 0.314, 0.0)),
        ("satara 18 17:58:11Z p39", M(24, 10, 6, 0.4, 0.2, 3.3, 20, 0.734, 0.471, 0.0)),
        ("satara 18 17:58:58Z p30", M(2, 1, 2, 1.0, 0.22, 3.7, 8, 0.454, 0.061, 0.0)),
        ("satara 18 17:59:13Z p30", M(0, 1, 1, 0.0, 0.0, 1.6, 0, 0.0, 0.0, 0.0)),
        ("satara 18 17:59:48Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 18:00:00Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 18:00:11Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 18:00:58Z p4", M(39, 10, 10, 0.39, 0.41, 0.4, 31, 0.761, 0.384, 0.0)),
        ("satara 18 18:01:09Z p4", M(8, 5, 3, 0.53, 0.33, 0.3, 12, 0.704, 0.412, 0.0)),
        ("satara 18 18:01:58Z p31", M(964, 96, 32, 0.31, 0.84, 6.3, 73, 0.5, 0.066, 0.0)),
        ("satara 18 18:02:09Z p2", M(11, 8, 3, 0.46, 1.0, 0.2, 1, 0.726, 0.284, 0.0)),
        ("satara 18 18:02:56Z p30", M(0, 1, 1, 0.0, 0.0, 0.9, 0, 0.0, 0.0, 0.0)),
        ("satara 18 18:03:08Z p30", M(0, 1, 1, 0.0, 0.0, 0.7, 0, 0.0, 0.0, 0.0)),
        ("satara 18 18:03:55Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 18:04:06Z p3", M(0, 1, 1, 0.0, 0.0, 0.2, 0, 0.0, 0.0, 0.0)),
        ("satara 18 18:04:53Z p4", M(82, 18, 16, 0.28, 0.55, 0.7, 20, 0.783, 0.213, 0.0)),
        ("satara 18 18:05:04Z p31", M(21, 8, 6, 0.44, 0.31, 2.1, 19, 0.642, 0.117, 0.0)),
        ("satara 18 18:05:51Z p2", M(3, 3, 1, 1.0, 0.5, 0.9, 3, 0.741, 0.406, 0.0)),
        ("satara 18 18:09:35Z p31", M(3, 2, 2, 0.75, 0.18, 1.4, 9, 0.302, 0.204, 0.0)),
        ("satara 18 18:30:48Z p4", M(111, 18, 16, 0.39, 0.32, 1.0, 45, 0.796, 0.205, 0.0)),
        ("satara 18 18:48:50Z p91", M(393, 57, 17, 0.41, 0.56, 8.1, 81, 0.849, 0.255, 0.0)),
        ("satara 18 18:53:55Z p4", M(174, 28, 18, 0.35, 0.57, 0.7, 33, 0.761, 0.236, 0.0)),
        ("satara 18 19:20:04Z p4", M(24, 8, 9, 0.33, 0.38, 0.6, 26, 0.765, 0.401, 0.0)),
        ("satara 18 19:32:53Z p126", M(685, 62, 21, 0.53, 0.99, 8.3, 5, 0.628, 0.172, 0.0)),
        ("satara 18 19:51:05Z p5", M(66, 12, 16, 0.34, 0.69, 1.5, 15, 0.219, 0.226, 0.0)),
        ("satara 18 20:03:15Z p126", M(218, 45, 15, 0.32, 0.96, 2.3, 4, 0.666, 0.291, 0.0)),
        ("satara 18 20:21:02Z p4", M(46, 9, 13, 0.39, 0.21, 0.7, 29, 0.704, 0.332, 0.0)),
        ("satara 18 20:31:10Z p91", M(344, 47, 18, 0.41, 0.87, 6.7, 23, 0.769, 0.229, 0.0)),
        ("satara 18 20:53:11Z p30", M(722, 80, 25, 0.36, 0.65, 5.8, 104, 0.789, 0.062, 0.0)),
        ("satara 18 20:59:49Z p64", M(120, 24, 14, 0.36, 0.24, 5.9, 69, 0.432, 0.34, 0.0)),
        ("satara 18 21:28:57Z p4", M(89, 21, 14, 0.3, 0.34, 1.6, 42, 0.76, 0.298, 0.0)),
        ("satara 18 21:43:49Z p33", M(342, 41, 20, 0.42, 0.37, 6.0, 107, 0.822, 0.295, 0.0)),
        ("satara 18 21:52:07Z p4", M(98, 19, 15, 0.34, 0.41, 0.9, 45, 0.74, 0.28, 0.0)),
        ("satara 18 22:07:05Z p4", M(93, 21, 12, 0.37, 0.3, 1.7, 47, 0.761, 0.273, 0.0)),
        ("satara 18 22:24:53Z p65", M(398, 59, 18, 0.37, 0.48, 6.7, 34, 0.64, 0.258, 0.12)),
        ("satara 18 22:44:52Z p4", M(83, 19, 15, 0.29, 0.39, 0.9, 29, 0.75, 0.362, 0.0)),
        ("satara 18 22:55:06Z p91", M(221, 35, 15, 0.42, 0.35, 9.9, 39, 0.849, 0.267, 0.0)),
        ("satara 18 23:03:51Z p4", M(223, 34, 19, 0.35, 0.62, 1.4, 38, 0.757, 0.292, 0.0)),
        ("satara 18 23:26:56Z p4", M(48, 11, 13, 0.34, 0.25, 0.9, 46, 0.799, 0.334, 0.0)),
        ("satara 18 23:41:55Z p4", M(138, 23, 21, 0.29, 0.45, 1.6, 49, 0.788, 0.288, 0.0)),
        ("satara 18 23:57:09Z p4", M(98, 20, 17, 0.29, 0.45, 1.1, 37, 0.76, 0.33, 0.0)),
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
#
# ADDED 4 SEP 2026: five new confirmed empties, four Talamati p41 and one
# Satara. Caps are UNCHANGED because none of the five leaks under the live
# config, so talamati night is now 8 of 25 rather than 8 of 21 and satara night
# opens at 0 of 1. A cap that does not move when the denominator grows is the
# only honest way to add negatives.
#
# RAISED 0 -> 3 FOR NOSSOB DAY ON 20 SEP 2026, deliberately, in the same
# delivery as NB_MAX 25 -> 250 and FILL_CMP 0.40 -> 0.30 at Nossob daylight,
# and said out loud here as the rule above requires. THE LEAKED ROWS, NAMED:
#   dawn 06:48 local   blob 61  13x6  fill 0.78  dom 0.26  dist 4.9  nblobs 48
#   dawn 07:18 local   blob 58  15x8  fill 0.48  dom 0.13  dist 3.6  nblobs 103
#   dawn 07:38 local   blob 308 61x7  fill 0.72  dom 0.68  dist 4.7  nblobs 52
# All three are rejected today on nblobs alone, 48/103/52 against NB_MAX 25,
# and all three reach the size and fill gates at 250. dawn 06:21 local still
# fails, on nblobs 9 it never needed NB_MAX for, so the cap is 3 and not 4.
#
# WHY IT IS ACCEPTED. This set is four frames. The Nossob review pass of
# 8-18 September 2026 yields 863 eye-confirmed NOSSOB DAYLIGHT EMPTY frames and
# 29 daylight priority frames. Measured 20 Sep 2026 by replaying the live
# is_hit over logs/nossob/ of 30 Aug to 18 Sep: the pair takes priority recall
# 6 -> 11 of 29 and leaks 142 -> 207 of 863. Three more leaks in a four-frame
# synthetic set is the same trade at 200x the sample size.
#
# THIS IS THE SAME SHAPE AS THE TALAMATI NATURAL_CAP RAISE OF 7 SEP 2026 and
# for the same reason: a real negative set now exists where none did when the
# cap was written.
#
# SATARA NIGHT 0 -> 5 ON 21 SEP 2026, IN THE SAME DELIVERY AS BLOB_MIN 90 -> 50,
# SAID OUT LOUD AS THE RULE ABOVE REQUIRES. The denominator went 1 -> 181 with
# the 180 reviewed night empties of 8 to 18 Sep. Of those, 4 leak under the old
# BLOB_MIN 90 and 5 under 50, so the cap splits 4 for new negatives the old
# config already leaked and 1 caused by this session's change. THE LEAKED
# ROWS, NAMED:
#   11 18:25:15Z p4   blob 122 24x13 fill 0.39 dom 0.54 dist 1.1  leaks at 90
#   17 20:30:06Z p2   blob 287 37x17 fill 0.46 dom 0.68 dist 5.5  leaks at 90
#   17 20:30:52Z p30  blob 97  16x13 fill 0.47 dom 0.49 dist 5.5  leaks at 90
#   17 20:34:15Z p2   blob 133 15x16 fill 0.55 dom 0.80 dist 4.1  leaks at 90
#   17 22:32:39Z p30  blob 57  9x8   fill 0.79 dom 0.80 dist 1.5  NEW AT 50
# The trade on this set is 2 animals for 1 empty. Measured on the full night
# log of 8 to 21 Sep the change adds 21 hits in 14 days, 18 of them unreviewed.
FP_MAX = {("nossob", "day"): 3, ("nossob", "night"): 43,
          ("talamati", "night"): 8, ("satara", "night"): 5}

# THE ONE THING THE 4 SEP EVENING BUNDLE SHIPPED WITHOUT, AND IT IS A GAP, NOT
# AN OVERSIGHT. There is still NO ("satara", "day") negative set in this file.
#
# Three archive frames are known to fire under the new config with the box on
# vegetation, all measured 4 Sep 2026 on the 24 Satara daylight frames of
# 3 September:
#   03 08:37:09Z p0  box on a fallen log and green scrub below a line of birds
#   03 10:25:08Z p0  box on a static patch of grass and scrub at the left edge
#   03 10:25:20Z p0  the same patch twelve seconds later, nothing inside it
# They are the shape of the false positives this bundle buys, and they belong
# here with a cap of 3 (they are there to MEASURE the cost, not to block the
# change, so a cap of 0 would be dishonest about a decision already taken).
#
# THEY ARE NOT IN THIS FILE BECAUSE THEIR blob, bw, bh, fill, dom AND nblobs
# ARE NOT WRITTEN DOWN ANYWHERE. They came out of a JPEG replay, and the
# session that ran it recorded the verdict and not the row. Inventing plausible
# numbers to fill the shape would put three guesses into the only file in the
# project that is allowed to reject a configuration.
#
# TO CLOSE THIS: pull those three rows out of logs/satara/20260903.csv by UTC
# timestamp and paste them in with FP_MAX[("satara", "day")] = 3. That is a
# five-minute job and it is worth doing before the 5 Sep volume read, because
# until it is done this harness can reward a Kruger daylight change (three
# REAL_ANIMAL rows, added tonight) and still cannot price one.
#
# NOTE ON REPLAY, so nobody closes this the wrong way: a positives-only archive
# builds its background out of other animal frames, so replayed nblobs runs
# about DOUBLE the live value and replayed dom about 0.09 low. Take these rows
# from the CSV, never from a re-run over the JPEGs.

# --- what a real daylight frame actually looks like --------------------------
# THE BUG THIS FIXES, FOUND 2 SEP 2026 AND CORRECTED 3 SEP.
#
# Every INJECTED row below passes five positional arguments to M(), so it is
# scored at `dist` 0.0 and `nblobs` 1. No real daylight frame has ever had
# either. The suite therefore reported 8/8 gemsbok and 5/5 elephant while the
# live detector caught nothing in daylight for four days, and it was
# structurally incapable of seeing a daylight failure.
#
# The injected rows are still worth keeping: they measure whether the GEOMETRY
# of an animal-sized target clears BLOB_MIN, DOM_MIN, ASP_MAX and the fill
# floors. That question is real and the answer is still 8/8. What they cannot
# do on their own is say whether the frame would ever reach those gates.
#
# So each set is now scored TWICE and both numbers are printed:
#   GEOMETRY  dist 0, nblobs 1, exactly as before. EXPECT_MIN.
#   FIELD     the camera's real daylight dist and nblobs. EXPECT_FIELD.
#
# The field values are medians measured on two independent days:
#   30 Aug - 2 Sep (in the 20260902d notes):  nblobs 37 / 56 / 140
#   2 Sep 13:03 - 3 Sep 04:49, 564 daylight rows across the three cameras:
#       nossob    195 rows  dist median 2.2  nblobs median 38
#       talamati  188 rows  dist median 6.8  nblobs median 55
#       satara    181 rows  dist median 10.7 nblobs median 129
# The two days agree to within one blob, so these are stable numbers.
#
# THIS IS A MEDIAN STANDING IN FOR THE FRAME'S OWN VALUE. The injected rows
# come from 30 Aug 13:39-14:07 UTC and that CSV has not been re-read, so the
# dist and nblobs of the exact frames each target was pasted into are not
# known. A median is the honest approximation, not a measurement of those
# frames. If the 30 Aug CSV is ever loaded, replace these per row.
FIELD = {
    "nossob":   dict(dist=2.2,  nb=38),
    "talamati": dict(dist=6.8,  nb=55),
    "satara":   dict(dist=10.7, nb=129),
}


def field(cam, m):
    """The same measured target, put back into a real daylight frame."""
    return dict(m, **FIELD[cam])


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

# GEOMETRY expectation: dist 0, nblobs 1. Does the shape clear the size,
# dominance, aspect and fill gates? Anything better is a bonus, anything worse
# is a bug.
EXPECT_MIN = {
    ("nossob", "day", "gemsbok 200x140"):   8,
    ("nossob", "day", "jackal 80x55"):      0,
    ("talamati", "day", "elephant 400x300"): 5,
    ("talamati", "day", "gemsbok 200x140"):  1,
}

# FIELD expectation: the same targets at the camera's real daylight dist and
# nblobs. THIS IS THE NUMBER THAT MATTERS AND IT IS ZERO EVERYWHERE.
#
# Measured 3 Sep 2026 with the live config. Every set goes to 0: at Nossob
# NB_MAX 25 rejects on nblobs 38, at Talamati DIST_MAX 6.0 rejects on dist 6.8
# before nblobs 55 is even reached. Nothing about the animal's geometry is
# consulted.
#
# This is a floor, not a ceiling: the test fails if a number FALLS below it,
# so raising these is the whole point of the daylight work. When NB_MAX and
# DIST_MAX are opened for daylight, this is the dict that moves, and the
# before/after pair here is the measurement to report.
#
# RAISED FOR TALAMATI, 4 SEP 2026 LATE EVENING, AND THIS IS THE FIRST TIME ANY
# NUMBER IN THIS DICT HAS MOVED OFF ZERO. Elephant 0 -> 5 of 5, gemsbok 0 -> 2
# of 5. The mechanism is exactly the one the block above describes: Talamati's
# real daylight median dist is 6.8, which used to be rejected by DIST_MAX 6.0
# before the target's geometry was ever consulted, and its median nblobs of 55
# used to be rejected by NB_MAX 25. At DIST_MAX 8.0 and NB_MAX 250 the frame
# now reaches the size, dominance, aspect and fill gates, and the elephant-sized
# target clears all of them.
#
# READ THIS FOR WHAT IT IS. It says a Talamati daylight frame can now be judged
# at all, which was not true for the first six days of this project. It does NOT
# say the detector will catch an elephant, because these are synthetic targets
# pasted into real frames and the dist and nblobs are population medians
# standing in for each frame's own value.
#
# NOSSOB STAYED AT ZERO UNTIL 20 SEP 2026 and no longer does. The sentence
# that used to sit here said Nossob was the untouched control in the 4 Sep
# bundle, which it was; NB_MAX 25 against a daylight median nblobs of 38 meant
# nothing about a Nossob daylight target's geometry was ever consulted. At
# NB_MAX 250 it is, and the gemsbok-sized target clears the size, dominance,
# aspect and fill gates: 0 -> 8 of 8. The jackal-sized target stays at 0 of 8
# and that is the honest reading of what this change buys at this camera: a
# gemsbok, not a jackal.
#
# READ THIS FOR WHAT IT IS, exactly as for Talamati above. It says a Nossob
# daylight frame can now be judged at all. It does not say the detector will
# catch a gemsbok, because these are synthetic targets pasted into real frames
# and the dist and nblobs are population medians standing in for each frame's
# own value.
EXPECT_FIELD = {
    ("nossob", "day", "gemsbok 200x140"):   8,
    ("nossob", "day", "jackal 80x55"):      0,
    ("talamati", "day", "elephant 400x300"): 5,
    ("talamati", "day", "gemsbok 200x140"):  2,
}


# --- KNOWN MISSES: REPORTED, NOT ASSERTED ------------------------------------
# ADDED 4 SEP 2026, from 48 archived JPEGs reviewed with the logged box drawn.
#
# WHY THESE ARE NOT `REAL_ANIMAL` ROWS. Every one is a confirmed animal with a
# CSV row, and they are the FIRST such rows either Kruger camera has ever had.
# They belong in REAL_ANIMAL on the merits. But each fails two or three gates,
# so adding them there turns this suite red on the day it ships and it stays
# red until a recall-first config lands, which is blocked behind the identify
# job. A permanently failing suite stops being read, and that is a worse
# outcome than a suite that reports honestly and passes.
#
# SO THEY LIVE HERE AND THEY ARE PRINTED EVERY RUN with the gate that stops
# each one. That does three jobs a comment could not:
#   1. it keeps the count of known misses visible instead of buried in a notes
#      file, so nobody re-derives it;
#   2. it turns any config change into an immediate readout of which known
#      animals it recovers, which is exactly the question every threshold
#      argument in this project has been trying to answer by hand;
#   3. when the recall-first config does land, this list moves to REAL_ANIMAL
#      wholesale and the REAL_MIN numbers are already known.
#
# THE PROMOTION RULE. A row moves out of here into REAL_ANIMAL the moment it
# is detected by the live config. If it is detected, it is a floor worth
# guarding; if it is missed, it is a target. Nothing stays here once it passes.
# ROWS THAT ARE CAUGHT HERE AND MUST NOT BE PROMOTED, with the reason. A row
# in this set is caught by the geometric gates and still missed by the live
# detector for a reason this harness cannot express, so promoting it would put
# a detection into REAL_MIN that the field cannot deliver.
NO_PROMOTE = {
    "03 09:54:05Z p15, spotted hyena lying, CLEARS DIST_MAX 8.0 but MIN_N n=2":
        "MIN_N 6: preset 15 was on its second frame ever, and every row in this "
        "file is scored at n=99",
    # ADDED 7 SEP 2026 with FILL_WIDE 0.30. Both rows are now caught and NEITHER
    # is a detection of its animal: the box is somewhere else in the frame, so
    # promoting them would guard a floor that measures nothing.
    "03 13:02:05Z p90, MANED MALE LION, below the floor, box elsewhere":
        "the recovered blob is a foreground shadow band at cy 0.799; the lion "
        "is at about cx 0.84, cy 0.57, outside the box",
    "03 14:40:58Z p0, warthog boar":
        "the box is the foreground grass below the animal, verified by eye "
        "7 Sep 2026; the boar is 24 x 14.4 blocks and outside it",
}

KNOWN_MISSES = {
    ("talamati", "day"): [
        # THE 03 10:22:08Z FOUR-ELEPHANT ROW WAS HERE UNTIL 4 SEP 2026 LATE
        # EVENING. NB_MAX 250, FILL_CMP 0.26 and DIST_MAX 8.0 between them
        # clear all three of the gates it failed, so it is PROMOTED into
        # REAL_ANIMAL under the rule above. Do not re-add it here.
        # Male lion with a full mane, in daylight. New for this camera. He is
        # about 6.8 x 5.1 blocks, roughly 20-25 filled, against BLOB_MIN 60.
        # THE FLOOR IS THE BINDING GATE HERE and no gate change touches it: the
        # row below is the logged blob, which is a foreground shadow band, not
        # the lion. Kept so the count of known misses is honest.
        ("03 13:02:05Z p90, MANED MALE LION, below the floor, box elsewhere",
         M(301, 45, 12, 0.56, 0.51, 5.9, 26, 0.799, 0.354, 0.15)),
        # Egyptian goose on the wall rim, new species. ~14 x 7 blocks, 55-70
        # filled, right on BLOB_MIN 60. Lost entirely to MIN_N: preset 106 was
        # on its THIRD frame ever, so n=3 is passed here deliberately and this
        # row is the only one in the file that tests MIN_N at all.
        ("03 06:52:13Z p106, Egyptian goose, MIN_N n=3",
         M(1729, 96, 54, 0.33, 0.85, 8.1, 76, 0.499, 0.060, 0.05)),
    ],
    ("talamati", "night"): [
        # SECOND CONFIRMED TALAMATI NIGHT ANIMAL. Elephant at the wall, domed
        # head, ear held out, trunk over the rim, tusk visible. About 15 x 10
        # blocks, 90-110 filled, so IT CLEARS BLOB_MIN 90. The logged blob is
        # the pool of floodlit ground in front of the wall; blob2 is 94.
        # "Largest blob wins" is what loses this animal, not the floor.
        ("03 18:32:53Z p41, ELEPHANT at the wall, box on floodlit ground",
         M(538, 71, 20, 0.38, 0.50, 18.9, 82, 0.822, 0.360, 0.30)),
    ],
    ("satara", "day"): [
        # THE 03 09:53:04Z THREE-HYENA ROW WAS HERE UNTIL 4 SEP 2026 EVENING.
        # It is now caught by the live config and has been PROMOTED into
        # REAL_ANIMAL under the promotion rule above. Do not re-add it here.
        #
        # The clearest hyena image in the project: lying chest-deep, head on
        # the rim, drinking. The box covers it.
        #
        # DELIBERATELY NOT PROMOTED, 4 SEP 2026 LATE EVENING, AND THIS IS AN
        # EXPLICIT EXCEPTION TO THE PROMOTION RULE ABOVE. At DIST_MAX 8.0 its
        # dist of 6.5 clears, and this harness scores every row at n=99, so it
        # now reports as caught. THE DETECTOR WOULD STILL MISS IT: preset 15
        # was on its SECOND frame ever and MIN_N 6 rejects it before any
        # geometry is consulted. Promoting it would put a detection in
        # REAL_MIN that the field cannot deliver. It stays here until either
        # MIN_N moves or the harness learns to score a row at its own n.
        ("03 09:54:05Z p15, spotted hyena lying, CLEARS DIST_MAX 8.0 but MIN_N n=2",
         M(868, 54, 31, 0.52, 0.58, 6.5, 48, 0.278, 0.060, 0.07)),
        # Warthog boar, close and side on, ~24 x 14 blocks. Five times the
        # floor. NB_MAX 140.
        ("03 14:40:58Z p0, warthog boar",
         M(840, 87, 31, 0.31, 0.47, 4.8, 140, 0.753, 0.323, 0.03)),
        # Banded mongoose, new species, walking the near rim. ~11 x 7 blocks.
        ("03 15:29:51Z p24, banded mongoose",
         M(1487, 87, 54, 0.32, 0.77, 4.6, 88, 0.482, 0.109, 0.00)),
        # Dark antelope, head down drinking, dorsal mane and high shoulders.
        # Consistent with a subadult blue wildebeest, NOT RESOLVED. Box covers
        # it loosely. ~11 x 12 blocks.
        ("03 13:01:28Z p9, wildebeest-type antelope, not resolved",
         M(515, 86, 21, 0.29, 0.63, 5.1, 122, 0.351, 0.080, 0.02)),
    ],
    ("satara", "night"): [
        # THE PIX_THR FRAME. A dark four-legged animal about 9.6 x 6.4 blocks
        # walks across open ground, legs and outline legible to the eye, and
        # the row reads px 49, blob 2. NO GATE IN cameras.py REACHES THIS. It
        # is here so that the number of known misses is not quietly understated
        # by leaving out the one that no threshold can fix.
        ("03 22:49:03Z p3, quadruped at px 49, blob 2, PIX_THR not a gate",
         M(2, 1, 2, 1.00, 1.00, 0.6, 1, 0.157, 0.060, 0.00)),
        # ADDED 21 SEP 2026. Drawn, box on the animal in all three, still missed
        # under BLOB_MIN 50. They are what the next Satara night change would
        # have to answer to, and why 50 was not pushed lower: 30 takes 22:30:56
        # at 9 leaks against 5.
        ("12 22:30:56Z p4, small animal at the top edge, below the floor",
         M(34, 6, 8, 0.71, 1.0, 0.6, 1, 0.054, 0.06, 0.03)),
        ("16 19:10:10Z p2, small animal, blob 8, below the floor",
         M(8, 5, 3, 0.53, 1.0, 0.3, 1, 0.655, 0.111, 0.0)),
        ("11 17:59:14Z p4, back leg only, aspect 2.25 on the wide branch",
         M(87, 8, 18, 0.6, 0.84, 1.2, 9, 0.678, 0.065, 0.0)),
    ],
}


def thr_for(cam, mode):
    return thresholds(CAMS[cam], 13 if mode == "day" else 22)


def first_gate(m, t):
    """Which gate rejects this row FIRST, in is_hit's own order. Reporting
    only. It exists so a known miss says WHY it is missed without anyone
    re-deriving it, and so that a config change shows immediately which gate it
    moved. Kept in step with is_hit by hand; if is_hit gains a gate and this
    does not, the label is wrong but no assertion depends on it."""
    if m["blob"] < 1:
        return "no blob"
    asp = max(m["bw"] / m["bh"], m["bh"] / m["bw"])
    lim = t["FILL_CMP"] if asp <= t["ASP_MAX"] else t["FILL_WIDE"]
    for name, bad, got, thr in (
            ("DIST_MAX", m["dist"] > t["DIST_MAX"], m["dist"], t["DIST_MAX"]),
            ("NB_MAX",   m["nb"] > t["NB_MAX"],     m["nb"],   t["NB_MAX"]),
            ("CY_MAX",   m["cy"] > t["CY_MAX"],     m["cy"],   t["CY_MAX"]),
            ("BACT_MAX", m["bact"] > t["BACT_MAX"], m["bact"], t["BACT_MAX"]),
            ("SAT_MAX",  m["bsat"] > t["SAT_MAX"],  m["bsat"], t["SAT_MAX"]),
            ("BLOB_MIN", m["blob"] < t["BLOB_MIN"], m["blob"], t["BLOB_MIN"]),
            ("BLOB_MAX", m["blob"] > t["BLOB_MAX"], m["blob"], t["BLOB_MAX"]),
            ("DOM_MIN",  m["dom"] < t["DOM_MIN"],   m["dom"],  t["DOM_MIN"]),
            ("FILL",     m["fill"] < lim,           m["fill"], lim)):
        if bad:
            return f"{name} ({got} vs {thr})"
    return "passes every gate (MIN_N is the only thing left)"


def main():
    bad = 0

    print("false positives on real empty-waterhole frames")
    for (cam, mode), rows in NATURAL.items():
        fp = [m for m in rows if is_hit(m, BIG_N, thr_for(cam, mode))]
        cap = NATURAL_CAP.get((cam, mode), 0)
        flag = "FAIL" if len(fp) > cap else "ok  "
        print(f"  {flag} {cam:9s} {mode:5s} {len(fp)}/{len(rows)} (cap {cap})")
        for m in fp:
            print(f"         leaked: blob{m['blob']} {m['bw']}x{m['bh']} "
                  f"fill={m['fill']} dom={m['dom']}")
        bad += max(0, len(fp) - cap)

    print("\ndetection of injected targets")
    print("  GEOMETRY = dist 0, nblobs 1. FIELD = the camera's real daylight")
    print("  dist and nblobs. Only FIELD says what the detector would do.")
    for (cam, mode, label), rows in INJECTED.items():
        t = thr_for(cam, mode)
        got = sum(is_hit(m, BIG_N, t) for m in rows)
        fld = sum(is_hit(field(cam, m), BIG_N, t) for m in rows)
        want = EXPECT_MIN[(cam, mode, label)]
        wantf = EXPECT_FIELD[(cam, mode, label)]
        ok = got >= want and fld >= wantf
        bad += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {cam:9s} {mode:5s} {label:18s} "
              f"geometry {got}/{len(rows)} (need >= {want})   "
              f"FIELD {fld}/{len(rows)} (need >= {wantf})")

    print("\nCONFIRMED animals in real frames (30 Aug - 18 Sep 2026)")
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

    print("\nKNOWN MISSES: confirmed animals the live config does NOT catch")
    print("            (reported, NOT asserted; see KNOWN_MISSES)")
    caught = 0
    total = 0
    for (cam, mode), rows in KNOWN_MISSES.items():
        t = thr_for(cam, mode)
        for label, m in rows:
            total += 1
            if is_hit(m, BIG_N, t):
                caught += 1
                print(f"       NOW CAUGHT  {cam:9s} {mode:5s} {label}")
                if label in NO_PROMOTE:
                    print(f"                   -> held back on purpose: "
                          f"{NO_PROMOTE[label]}")
                else:
                    print(f"                   -> PROMOTE THIS ROW TO REAL_ANIMAL")
            else:
                print(f"       missed      {cam:9s} {mode:5s} {label}")
                print(f"                   first gate: {first_gate(m, t)}")
    print(f"       {caught}/{total} of the known misses are now caught")

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
