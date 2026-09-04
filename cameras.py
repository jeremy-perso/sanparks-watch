"""
Camera registry.

One entry per SANParks still cam. Everything that differs between cameras lives
here; watch.py itself is camera-agnostic.

`thr` overrides watch.py's DEFAULTS during daylight, `thr_night` overrides it
again once the local hour falls inside `night`. Anything you leave out is
inherited, so each block only lists what actually differs.

THE ONE THING TO KNOW BEFORE EDITING THESE
------------------------------------------
`DOM_MIN` (the largest blob must account for this share of all change) is a
NIGHT rule. It works at Nossob after dark because the floodlit scene is nearly
static, so an animal really is most of the change in the frame.

In daylight it is false on both cameras. Measured 30 Aug 2026, 13:39-14:07 UTC:
every daylight frame has 100-500 changed blocks from wind, grass and moving
sun. Injecting a gemsbok-sized target into real frames and real backgrounds,
`dom` never got above 0.45, so with DOM_MIN=0.45 nothing was ever detected -
not a gemsbok, not an elephant. Daylight configs below therefore set DOM_MIN
to 0 and lean on blob size, solidity and the smear rejector instead.

Threshold provenance:
  nossob   night - 101 real night frames, 24 Aug 2026, plus 493 real night
                   frames 31 Aug - 1 Sep 2026 with every one of the 77 hits
                   pulled back and looked at. 9 contained animals (a lion, 4
                   jackal frames, an owl) and 68 did not. The night config is
                   therefore now calibrated against real animals AND real
                   empties, which is new. Its honest precision on that night
                   is 9 of 77 hits, improving to 9 of 66 with the FILL_WIDE
                   change below, which costs no animal.
  nossob   day   - 18 real daylight frames, 30 Aug 2026. 0 false positives,
                   8/8 injected gemsbok, 0/8 jackal (the daylight limit).
  talamati day   - 13 real daylight frames, same window. 0 false positives,
                   5/5 injected elephant, 1/5 gemsbok.
  talamati night - 226 real night frames, 30-31 Aug 2026. The starting-point
                   guess fired on 46 of them (20%) and not one contained an
                   animal, so it has been retuned against that log.

TWO NEW GATES, ADDED 31 AUG 2026
--------------------------------
`DIST_MAX` and `NB_MAX` live in watch.py's DEFAULTS and are inherited here.
Both came out of 906 real frames logged 30-31 Aug 2026:

  DIST_MAX  a frame may be matched to a preset (SIG_TOL) and still be too poor
            a match to decide on. At Talamati the median changed-pixel count
            climbs from 183 (dist 0-3) to 26908 (dist 18-25). Judging only
            frames within 6 removed 30 of Talamati's 53 hits and kept every
            confirmed Nossob animal (worst was the 19:02 jackal at dist 5.2).

  NB_MAX    every confirmed animal scored nblobs <= 17 (the 30 Aug dove flock);
            the four confirmed Nossob dawn false positives scored 48, 52, 103
            and 141. Diffuse change fragments, animals do not.
"""

CAMERAS = [
    {
        "name":  "nossob",
        "label": "Nossob waterhole (Kgalagadi)",
        "url":   "https://hibiscus.sanparks.org/webcams/nossob.jpg",
        "tz":    2,                      # park local = UTC + this
        # Round the clock as of 31 Aug 2026, widened from [(5,10),(15,21)].
        # Daylight detection is proven only on synthetic targets and one dove
        # flock, and a daylight animal is much easier to identify by eye, so
        # the daylight hours are the point. The small hours come along for free
        # and will finally characterise the generator gap.
        "active": [(0, 24)],             # local hours to watch, half-open
        "night":  (18, 6),               # local hours treated as night

        # Open floodlit sand. Few presets and they repeat: in 19 minutes the
        # busiest view came round 10 times, so backgrounds converge quickly.
        # Daylight noise is low by comparison, median 1.9k changed pixels out
        # of ~75k visible (2.5%), largest natural blob 66 blocks once a preset
        # has settled. An injected gemsbok makes 49-96 blocks, so size is the
        # discriminator that actually works here.
        "thr": {
            "DOM_MIN":   0.0,    # see the note above: dom is a night rule
            "BLOB_MIN":  45,     # natural daylight blobs top out at 66...
            "FILL_CMP":  0.40,   # ...and the ones that big are thin smears
            "FILL_WIDE": 0.62,
            "ASP_MAX":   2.4,
            # Dawn is this camera's worst hour. Between 06:00 and 08:00 local
            # the sun rises AND the camera swaps its IR-cut filter in, so every
            # preset background is stale at once. Measured 31 Aug: preset 3 ran
            # blob 344 -> 308 -> 290 -> 220 -> 66 -> 26 over 90 minutes as the
            # background caught up, and four of those frames scored hits with
            # nothing in them. They fragment (nblobs 48-141), so NB_MAX is what
            # catches them; all four are rejected at 25.
            "NB_MAX":    25,
            "DIST_MAX":  6.0,
        },

        # The 24 Aug night calibration, with one change on 1 Sep 2026: see
        # FILL_WIDE below.
        "thr_night": {
            "SIG_TOL":   11,
            "PIX_THR":   24,
            "BLK_MIN":   6,
            "MIN_N":     4,
            "BLOB_MIN":  3,
            "BLOB_MAX":  600,
            "DOM_MIN":   0.45,
            # Raised from 2.4 on 30 Aug evidence. A jackal standing broadside
            # on the far bank measured 11x4 blocks, aspect 2.75, fill 0.45: it
            # fell to the smear rejector's wide branch and was thrown away. The
            # 24 Aug night smears that ASP_MAX exists to reject run 3.0 to 6.4,
            # so 3.0 sits below all of them and selftest still leaks nothing.
            "ASP_MAX":   3.0,
            "FILL_CMP":  0.32,
            # 0.62 -> 1.01 on 1 Sep 2026. `fill` can never exceed 1.00, so this
            # makes the smear rejector's wide branch unreachable and turns
            # ASP_MAX 3.0 into a HARD aspect ceiling at night.
            #
            # Measured: all 17 confirmed Nossob night animals (the 8 in this
            # file's history plus the 9 of 31 Aug - 1 Sep, which include a
            # lion) have aspect 1.00 to 2.75. The worst case, 2.75, is the
            # broadside jackal ASP_MAX was raised to 3.0 for in the first
            # place, so the margin is unchanged. Meanwhile 11 of the 68
            # confirmed-empty night hits of that same night were long thin
            # smears at aspect 3.1 to 13.0 sneaking through on fill: the
            # floodlit trough rim on preset 14 (13x2, 15x2, 52x4) and the
            # water-line bar on preset 12.
            #
            # 11 false positives removed, 0 of 17 confirmed animals lost. This
            # is the only zero-cost gate in the whole night log.
            #
            # DAYLIGHT MUST NOT COPY THIS. The 31 Aug dove flocks measured
            # aspect 2.9 to 5.7 and the Talamati zebra group 2.88; they need
            # the wide branch. This is a night-only change.
            "FILL_WIDE": 1.01,
            "NB_MAX":    25,
            # 6.0 -> 8.0 AT NIGHT ONLY, 3 SEP 2026 EVENING. Daylight `thr`
            # above keeps 6.0; this key only exists here.
            #
            # THE MISS THAT FORCED IT. 02 21:16:00 UTC, p15, n=287, dist 7.2,
            # blob 252, 17x27 blocks, fill 0.55, dom 0.49, cx 0.581, cy 0.254,
            # bact 0.063, nblobs 7, hit=0. Reference frame
            # frames/nossob/20260902/211600_p15_blob0252_f0.55.jpg, burnt-in
            # 23:07:46. THREE LIONS: one drinking at the left, one drinking
            # dead centre with a full reflection, a third standing behind with
            # only its legs and belly in frame. The logged box lands squarely
            # on the centre animal's head, chest and reflection. This is a
            # valid measured row and a SINGLE-GATE miss: DIST_MAX is the only
            # gate it failed.
            #
            # THE MECHANISM, AND IT IS THE UNCOMFORTABLE PART. A large animal
            # close to the camera changes the 16x9 fingerprint enough to raise
            # its OWN `dist`. Measured on the 681 Nossob night rows of 2/3 Sep:
            #     blob   0-3    394 rows   dist median 0.5   p90  1.1
            #     blob   3-10   121 rows   dist median 0.6   p90  1.7
            #     blob  10-50    92 rows   dist median 1.3   p90  3.7
            #     blob  50-200   49 rows   dist median 3.9   p90  6.7
            #     blob 200+      25 rows   dist median 7.4   p90 10.1
            # DIST_MAX is therefore not a neutral quality filter at night: it
            # penalises the biggest, closest and most interesting animals
            # hardest. The 01 01:57:09 lion already sat at 5.4, inside 6.0 by
            # 0.6, and that was the warning nobody read.
            #
            # WHAT IT COSTS. Nothing measurable. Swept over the same 681 rows
            # with every other gate live:
            #     DIST_MAX  6.0 -> 82 hits
            #     DIST_MAX  7.5 -> 83
            #     DIST_MAX  8.0 -> 83
            #     DIST_MAX 11.0 -> 83
            # Twenty-three rows sit in the 6.0 to 8.0 band and TWENTY-TWO are
            # rejected by a later gate anyway (NB_MAX on the dusk and dawn
            # fragmentation, DOM_MIN, BACT_MAX, the fill floors). The
            # twenty-third is the lion frame. One animal recovered, zero false
            # positives added, on one night of 681 rows.
            #
            # WHY 8.0 AND NOT 11.0. 11 costs nothing on this night either, and
            # 11 is SIG_TOL, so it would abolish the night dead band outright.
            # Not taken: it would leave no margin at all between "belongs to
            # this preset" and "can be judged on it", on one night's evidence.
            # 8.0 clears the lion at 7.2 by 0.8. Revisit with a second night.
            #
            # IT DOES NOT CONFOUND THE BACT_MAX MEASUREMENT. Replayed at
            # DIST_MAX 8.0 that gate removes 16 of 99 rather than 15 of 97.
            # The inert-versus-live replay is valid under either value.
            "DIST_MAX":  8.0,
            # NEW 1 Sep 2026 evening. The blob centroid must sit above this
            # fraction of frame height. Inert everywhere else (DEFAULTS 1.01).
            #
            # MECHANISM FIRST, THEN THE NUMBER. All 77 Nossob night hits of
            # 31 Aug - 1 Sep were cropped to their logged cx/cy/bw/bh and
            # sorted by cy. From cy 0.68 downwards essentially every crop is
            # out-of-focus foreground grass: the bottom third of these framings
            # is near-field grass in front of the pan, and the trough the
            # animals actually drink at sits in the middle band. The ~35
            # swaying-grass false positives the notes counted are a POSITION
            # family, not a size or brightness family.
            #
            # Scored on the 9 confirmed animals and 68 confirmed empties of
            # that night:
            #    cy < 0.70  keeps 9/9, removes 29/68
            #    cy < 0.85  keeps 9/9, removes 21/68
            #    cy < 0.90  keeps 9/9, removes 19/68
            # 0.75, 0.80 and 0.85 all remove the same 21, so 0.85 is chosen:
            # it is the widest value that costs nothing measurable.
            #
            # 0.70 IS DELIBERATELY NOT TAKEN. The lowest confirmed animal is a
            # jackal at a tree base on p11 at cy 0.698, so 0.70 would have a
            # margin of 0.002 on a set of nine. 0.85 leaves 0.15.
            #
            # HONEST LIMITS. cx/cy only exist from 31 Aug 12:48 UTC, so this
            # gate can be scored against 9 confirmed animals, not the full 17,
            # and it is fitted and tested on the same nine. It is a positional
            # rule on a PTZ camera: if the framing library shifts, re-check it.
            # DAYLIGHT MUST NOT COPY THIS until there is a labelled daylight
            # set; the doves feed all round the pan edge, not just above it.
            "CY_MAX":    0.85,

            # NEW 2 Sep 2026 evening. Ceiling on the LOGGED `bact` column: the
            # mean activity-EMA of the blob's own blocks. Inert everywhere else
            # (DEFAULTS 1.01).
            #
            # NAMING, BECAUSE THE NOTES GET THIS WRONG. The 2 Sep notes call
            # this "ACT_MAX 0.21". ACT_MAX is already taken: it is the per-block
            # veto in watch.py, currently 0.60, and it decides which blocks may
            # form a blob at all. Setting THAT to 0.21 would re-cut every blob
            # and change blob, fill, dom, nblobs and cy on every frame. This is
            # a separate key.
            #
            # MECHANISM FIRST. On preset 13 a lion drank at 02 01:40:00 UTC:
            # blob 156, 23x11, cx 0.091, cy 0.323, bact 0.064. Seventy minutes
            # later four hits fire on an almost identical box in an empty
            # frame: 02:53:16 blob 130 (21x11, cx 0.091, cy 0.316), 02:56:17
            # blob 106, 02:58:56 blob 72, 02:59:08 blob 25, at bact 0.252,
            # 0.305, 0.350 and 0.392. Same preset, same place, same shape,
            # nothing in frame. Geometry cannot separate those; bact does, by a
            # factor of four.
            #
            # MEASURED 2 Sep 2026 on the 94 Nossob night hits of 1/2 Sep, the
            # only night carrying the column. 29 of those hits are animals
            # documented in animals.md with a box that lands on the animal:
            #   bact median 0.091, max 0.209 (a lion, 02 01:43:08).
            # Of the other 65 hits, 17 score above 0.21.
            #   BACT_MAX 0.21 -> 29/29 animals kept, 17 hits removed
            #   BACT_MAX 0.23 -> 29/29 kept, 15 removed
            #   BACT_MAX 0.25 -> 29/29 kept, 12 removed
            # The hare of 01 19:35:08, the one confirmed miss of the night,
            # scores bact 0.062 and is not touched by this gate either way.
            #
            # THREE HONEST LIMITS.
            #  1. SAME-SET FIT. 0.21 is one tick above the maximum of the 29
            #     animals it is scored on. There is no out-of-sample test. A
            #     second night of 26-column data is the thing that settles it.
            #  2. NO HISTORIC ANIMAL CARRIES bact. Every confirmed animal
            #     before 1 Sep is on an 18- or 23-column row, so this cannot be
            #     scored against the springbok, the 30 Aug owls or the 30 Aug
            #     jackals. In selftest they default to bact 0.0 and pass, which
            #     is a convention, not evidence.
            #  3. NIGHT ONLY, LIKE DOM_MIN. The one confirmed daylight animal
            #     carrying the column (dawn bird flock, 02 04:59:11 UTC, p3,
            #     blob 311) has bact 0.314. A global 0.21 would kill the only
            #     daylight animal this detector has caught since 30 Aug.
            #
            # NOT AT TALAMATI. Talamati has zero confirmed night animals across
            # four nights, so a gate fitted purely on its negative set has
            # nothing to protect. Three of its ten night empties score bact
            # 0.063 to 0.081, squarely inside the Nossob animal band.
            "BACT_MAX":  0.21,

            # SAT_MAX IS DELIBERATELY NOT SET HERE. Measured 2 Sep 2026 on the
            # same 94 hits: SAT_MAX 0.25 keeps 29/29 animals and removes 9 more
            # hits, 8 of them floodlit insects on preset 14 at bpk 255 and bsat
            # 0.50 to 1.00. Combined with BACT_MAX 0.21 it removes 24 of the 65
            # rather than 17.
            #
            # It is held back on purpose so the next night is a clean
            # out-of-sample test of BACT_MAX alone. The floor is hard, not
            # chosen: the highest bsat on any confirmed animal in the whole
            # archive is 0.24, two barn owls side by side on the concrete block
            # at 01 23:46:58 with four eyeshine points in a 3x7 box. Any
            # SAT_MAX below 0.25 takes an owl.
        },
    },
    {
        "name":  "talamati",
        "label": "Talamati waterhole (Kruger)",
        "url":   "https://hibiscus.sanparks.org/webcams/talamati.jpg",
        "tz":    2,
        "active": [(0, 24)],             # widened 31 Aug, see nossob above
        "night":  (18, 6),

        # A far harder scene: dense bush, tall grass, dappled sun, and a much
        # wider PTZ sweep that includes open grassland pans. Against Nossob
        # over the same 20 minutes: 2.5x the changed pixels (median 4.8k of ~75k,
        # 6.4%), natural blobs up to 455 blocks against Nossob's 66, and 13
        # presets discovered where Nossob found 8.
        #
        # Be honest about what this config is: a data-collection setting. An
        # injected elephant is caught 5/5, a gemsbok 1/5, and anything smaller
        # not at all. The frames worth looking at come from COLLECT=top
        # archiving the biggest blobs, not from these hits.
        "thr": {
            # SIG_TOL 25 -> 11 ON 4 SEP 2026. THIS IS THE ONE DECISION CHANGE
            # IN THIS BUNDLE. It is the same change made at Satara on 3 Sep,
            # made here on direct evidence rather than by analogy.
            #
            # WHAT 25 WAS FOR, and why it is now wrong. New-preset distances on
            # 30-31 Aug came in two clusters: 11.8, 11.9, 14.9, 19.9, then
            # nothing until 50.2. 25 sat in the empty gap and stopped a
            # fragmentation that was starving every background of samples. That
            # reading was right about the fragmentation and wrong about what
            # the low cluster meant. It is not one view learned twice.
            #
            # THE PROOF, 4 SEP 2026, and it is two JPEGs.
            #   frames/talamati/20260903/183253_p41_blob0538_f0.38.jpg is the
            #   reservoir wall, with a confirmed elephant standing at it.
            #   frames/talamati/20260903/183305_p41_blob0621_f0.31.jpg, logged
            #   TWELVE SECONDS LATER UNDER THE SAME PRESET ID, is a marula
            #   trunk over open grass with no wall anywhere in the frame.
            #
            # Not a pan. Two camera positions. `bright` separates them over all
            # 291 p41 rows with a clean empty band:
            #   reservoir wall     96 rows (33%)  bright 107-118
            #   tree over grass   195 rows (67%)  bright  84- 96
            #   in the 98-105 band: FOUR rows out of 291.
            # The five frames reviewed by eye land exactly where the split
            # predicts: 110.1, 109.1, 114.3 wall; 94.7, 94.0 grass.
            #
            # Both views sit at dist 13.6 and 13.3. That is the confirmation,
            # not a puzzle: one preset holds ONE background array, so every
            # frame of either view is diffed against a blend of both and all of
            # them are wrong by the same amount. It also explains why a 35
            # minute elephant visit produced one usable frame: only a third of
            # "p41" is pointed at the wall at all.
            #
            # WHY 11 SPLITS IT, AND THIS IS ARITHMETIC, NOT A FORECAST.
            # The `dist` column IS the signature match distance: watch.py sets
            # m["dist"] = bd, and bd is what SIG_TOL gates on. So the log
            # already says what a different SIG_TOL would have done.
            #   p41: 69.8% of its 291 rows have dist > 11 (min 0.2, max 21.1).
            # Every one of those forks a new preset at SIG_TOL 11.
            #
            # WHAT IT COSTS, measured on 1,638 Talamati rows of 3-4 Sep:
            #   23.2% of all Talamati rows have dist > 11 and will fork on the
            #   first pass. Compare the two cameras already at 11 over the same
            #   29 hours: Nossob 0.0% above 11, Satara 2.6%. Those are the
            #   converged end states this is aiming at.
            #
            # WHAT IT BUYS. Talamati's dead band (6 < dist <= SIG_TOL: admitted
            # to a preset, refused judgement by DIST_MAX) is 41% of daylight
            # rows and 46% of night rows today. At Satara the same change took
            # the dead band from 90% of daylight rows to 11%.
            #
            # THE RISK THAT DID NOT EXIST AT SATARA. Satara had no confirmed
            # animals to lose. Talamati has a confirmed night elephant and
            # eight confirmed daylight species. The expected direction is
            # recovery, because animals.md already attributes the 30 Aug
            # elephant miss to "SIG_TOL 25 lumps several framings into one
            # preset and the background never converges". It is still a change
            # to a camera with something at stake.
            #
            # THE SECOND RISK, AND IT IS WHY PRESET_CAP MOVED. Forking 23% of
            # frames creates presets fast, and every new preset is deaf for
            # MIN_N frames. Five species have already been lost that way (see
            # webcammonitoringnotes20260904c.md section 5). MIN_N is NOT being
            # touched in the same bundle: one decision change at a time, and
            # the MIN_N question needs its own measurement. But watch.py's
            # PRESET_CAP goes 120 -> 200 in this bundle as insurance, so the
            # experiment cannot be confounded by eviction of load-bearing
            # presets halfway through.
            #
            # HOW TO READ TOMORROW'S LOG. Three numbers, in this order:
            #   1. share of rows with dist > 11. Falling toward Satara's 2.6%
            #      means it worked. Staying near 23% means the views are not
            #      separable by this fingerprint and `bright` is the next idea
            #      (see the note at the end of this dict).
            #   2. p41. It should stop existing as a single busy preset. If two
            #      new presets appear with bright clusters at ~110 and ~93 and
            #      each converges to dist < 3, that is the whole hypothesis
            #      confirmed.
            #   3. distinct preset ids per day, against PRESET_CAP 200.
            "SIG_TOL":   11,
            "PIX_THR":   24,     # the value all the numbers above were measured at
            "MIN_N":     6,      # backgrounds converge slower here
            "DOM_MIN":   0.0,
            "BLOB_MIN":  60,     # below this it is always vegetation
            "BLOB_MAX":  900,
            "ASP_MAX":   2.2,
            # 0.44 -> 0.26 ON 4 SEP 2026 EVENING, TOGETHER WITH NB_MAX BELOW.
            # THE TWO ARE ONE CHANGE AND MUST BE READ TOGETHER. Jeremy
            # authorised an explicit exception to the one-change-per-session
            # rule for this pair on 4 Sep 2026.
            #
            # WHY THEY ARE INSEPARABLE, measured on the 650 Satara daylight
            # rows of 4 Sep against the two frames whose box is demonstrably on
            # a bird (the same scene physics applies here):
            #     live                    2 hits / 650   0 of 2 birds
            #     NB_MAX 250 alone        6 hits / 650   0 of 2 birds
            #     FILL_CMP 0.26 alone     2 hits / 650   0 of 2 birds
            #     BOTH                   52 hits / 650   2 of 2 birds
            # Each gate alone catches nothing and moves volume by at most four
            # frames, so there is no clean single-gate measurement to confound.
            #
            # WHY 0.26 AND NOT HIGHER. The two measured Satara daylight bird
            # rows sit at fill 0.28 and 0.38; the Talamati daylight elephant of
            # 03 10:22:08 sits at 0.28. 0.26 clears 0.28 by two hundredths.
            #
            # THE PRICE, STATED BEFORE IT IS PAID. Talamati daylight goes from
            # 6 hits in 700 rows (0.9%) to 85 (12.1%); Satara from 2 in 650
            # (0.3%) to 52 (8.0%). About 137 extra hits a day across the two
            # cameras, every one archived, order 20 MB a day into git history.
            # Almost none of them will be animals. That volume is what stage 2
            # is for: SpeciesNet returned `blank` on all ten Talamati confirmed
            # empty night hits at max confidence 0.13, and scored 85/89 on real
            # animals.
            #
            # IT LEAKS TWO OF THE THIRTEEN TALAMATI DAYLIGHT NATURALS in
            # selftest.py (blob 147 at fill 0.38 and blob 101 at fill 0.29).
            # That is the measured cost, not a surprise, and selftest.py now
            # carries a NATURAL_CAP of 2 here saying so.
            #
            # NIGHT MUST NOT COPY THIS. thr_night below keeps FILL_CMP 0.36.
            "FILL_CMP":  0.26,
            "FILL_WIDE": 0.72,   # smear naturals measured 0.36-0.65
            # SIG_TOL 25 stopped the fragmentation but it also lumps framings
            # up to 25 apart into one preset, and a frame 15-25 from its own
            # background is not that view. All 7 daylight hits of 30-31 Aug sat
            # above dist 6 and none contained an animal.
            #
            # 6.0 -> 8.0 AT TALAMATI DAYLIGHT, 4 SEP 2026 LATE EVENING.
            #
            # THIS BLOCK USED TO SAY DIST_MAX 8.0 RECOVERS NOTHING. That was
            # true and it is no longer true, and the reason is worth reading
            # before anyone reverts it. The claim rested on the one Talamati
            # daylight row whose box is on the animals (03 10:22:08, four
            # elephants at the reservoir wall including a calf, blob 242,
            # 34x25, cx 0.612, cy 0.568, n=36) failing THREE gates at once:
            # DIST_MAX 6.0 against 7.6, NB_MAX 25 against 38, and FILL_CMP
            # 0.44 against fill 0.28. Opening any one of the three recovered
            # nothing, so each in turn looked worthless.
            #
            # NB_MAX AND FILL_CMP WERE OPENED EARLIER THIS EVENING. DIST_MAX
            # 6.0 is now the ONLY gate that row fails, and 7.6 < 8.0 clears it
            # by 0.4. It goes from a three-gate miss to a single-gate miss to a
            # detection, and it is the only Talamati daylight row in the whole
            # project that measures an animal.
            #
            # 8.0 AND NOT HIGHER. The Egyptian goose of 03 06:52:13 sits at
            # dist 8.1 and is still missed, deliberately: that row is a
            # whole-frame blob (bw 96) on a preset's third frame ever, so it
            # measures nothing and recovering it would be recovering noise.
            # 8.0 is also the value already live at Nossob night, so the file
            # gains no new number.
            #
            # WHAT IT COSTS, AND THIS IS THE HONEST PART. Measured 4 Sep under
            # the OLD NB_MAX 25 / FILL_CMP 0.44, DIST_MAX 8.0 added about 20
            # Talamati and 4 Satara hits a day. That measurement no longer
            # applies, because the two gates in front of it are now open, and
            # the cost under the new config HAS NOT BEEN MEASURED. It will be
            # larger. Expect it in tomorrow's volume read.
            #
            # selftest.py CANNOT PRICE THIS CHANGE AND THAT IS NOT A BUG IN
            # THE ARGUMENT, IT IS A LIMIT OF THE HARNESS. Every one of the 13
            # Talamati daylight NATURAL rows is scored at dist 0.0, because
            # they predate the dist column. No value of DIST_MAX can ever make
            # one of them leak. The leak count staying at 2 across this change
            # is therefore not evidence of anything.
            #
            # IT REMAINS DECOMPOSABLE FROM TOMORROW'S LOG. is_hit has no side
            # effects and the background update at the end of handle() runs
            # unconditionally, so DIST_MAX changes which rows are flagged and
            # nothing else. Replaying tomorrow's CSV at 6.0 and at 8.0 gives
            # the exact hit count attributable to this gate alone, the same way
            # 2,978 rows were replayed on 4 Sep with zero disagreement against
            # the logged flag.
            "DIST_MAX":  8.0,
            # 25 -> 250 ON 4 SEP 2026 EVENING. The second half of the FILL_CMP
            # change above; neither half works alone.
            #
            # WHY NB_MAX 25 HAD TO GO. It is the FIRST gate on every large
            # Kruger daylight animal, before size, shape or position is
            # consulted, and it fires on a converged background: the Satara
            # hyena group at nblobs 189 with dist 3.6, the warthog boar at 140,
            # the banded mongoose at 88 and 164, the wildebeest-type antelope
            # at 122, this camera's own four elephants at 38. A dozen birds
            # moving independently on the rim is a dozen blobs before the
            # vegetation is counted, and seven forum frames diffed against a
            # median background of their own view (dist 4.8-5.4, so the
            # mismatch is removed by construction) still score nblobs 101 to
            # 140. SIG_TOL will not help this. It is the scene.
            #
            # WHY 250 AND NOT 200. The one Satara daylight row whose box is
            # demonstrably on a bird reads nblobs 217. At 200 that row is lost.
            #
            # WHAT THIS IS NOT. It is not a claim that fragmentation is
            # harmless. It is a decision to move the empty-frame filter from
            # stage 1 geometry to stage 2 identification, taken on 4 Sep 2026.
            "NB_MAX":    250,
            # THE ALTERNATIVE THAT WAS MEASURED AND REJECTED, 4 Sep 2026.
            #
            # `bright` separates p41's two views perfectly and the preset
            # fingerprint cannot see it, because analyse() subtracts the mean
            # before building it (watch.py: `s = s - s.mean()`). Adding a
            # brightness term to the match distance looked like the root-cause
            # fix. IT IS NOT, and the reason is worth keeping so that nobody
            # proposes it again.
            #
            # Within-preset `bright` spread (p10 to p90) on presets with 40+
            # rows, 3-4 Sep, is far LARGER than the ~15 that separates p41's
            # two views:
            #   nossob daylight   p83 69.7, p80 69.6, p65 65.5, p39 65.4
            #   talamati daylight p25 57.2, p0 49.2, p98 48.0, p90 47.2
            #   median across all presets: nossob 30.6, talamati 26.3
            # A single framing swings 30 to 70 grey levels between dawn and
            # dusk. Any brightness term large enough to split p41 would fork a
            # new preset every hour of every day on every camera.
            #
            # At NIGHT it is tight (nossob p12 3.3, p13 6.6; satara p4 6.5,
            # p30 3.7) so a NIGHT-ONLY brightness term is not dead. It is also
            # not needed unless SIG_TOL 11 fails, and it must not be tried in
            # the same bundle as this one.
        },

        # NOW MEASURED, 226 night frames on 30-31 Aug 2026. Two findings.
        #
        # The waterhole IS lit: an IR floodlight, and the archived frames show
        # insects streaking through it exactly as at Nossob.
        #
        # The starting-point guess was far too loose. It fired on 46 of 226
        # frames (20%). Most were insects, an overexposed blowout on the bright
        # presets, and preset 9 diffing against a smeared background. DIST_MAX
        # takes 30 of those, BLOB_MIN 45 takes most of the rest, leaving 11.
        #
        # CORRECTED 2 SEP 2026. This block used to claim that NOT ONE of those
        # frames contained an animal. That is false. Two p9 night frames of
        # 30 Aug, burnt-in 20:23:46 (blob 632, fill 0.48) and 20:24:00 (blob
        # 334, fill 0.68), UTC 18:31:50 and 18:32:14, contain an ELEPHANT that
        # visibly moves between them, and the second is in hits/, so it scored.
        # That is Talamati's first confirmed night animal.
        #
        # NEITHER ROW MEASURES THE ANIMAL. Settled from the 30 Aug CSV the
        # same day: 18:32:14 is bw 35 x bh 14, a 700x280 px box, and 18:31:50
        # is 83x16, a 1660x320 px box. The elephant is about 160x210 px. Both
        # boxes are illumination bands with an animal inside them, exactly like
        # the p16 lion at Nossob, so they are documented in animals.md as
        # "seen but not measured" and MUST NOT be used to tune anything.
        #
        # IT CHANGES NO THRESHOLD HERE, but it does expose one thing worth
        # knowing: under the LIVE config that whole visit would be silent.
        # Both frames are now rejected three times over (DIST_MAX 12.8 and
        # 18.2 against 6.0, NB_MAX 36 and 30 against 25, and the fill floor),
        # and across 18:25-18:45 UTC not one p9 frame matched its background
        # closer than 8.5, ranging to 19.5. The twelve frames in that window
        # that DO pass DIST_MAX are on presets 7, 10, 12 and 14, pointing
        # elsewhere, with blobs of 0 to 14.
        #
        # The 30 Aug hit was an artefact of a config that had no DIST_MAX yet.
        # The problem is not DIST_MAX; it is that p9's background never
        # converged, which is what SIG_TOL 25 does when it lumps several
        # framings into one preset. NOT ACTED ON: there is still no row that
        # measures a Talamati animal to score a change against.
        #
        # BLOB_MIN 45 is the honest weak point. Nossob's real night animals
        # measured 4 to 51 blocks, so 45 would miss most of them there. It is
        # set high here only because Talamati has never yet produced a
        # confirmed animal to calibrate against, and a 20% hit rate of pure
        # noise is worse than a quiet log. Lower it the moment there is one.
        "thr_night": {
            "PIX_THR":   26,
            # 45 first, then 90 on 31 Aug after all nine surviving night hits
            # were pulled back and looked at: every one was an out-of-focus
            # insect near the lens, largest blob 81 blocks. 90 clears them.
            #
            # This is a stopgap and it is a guess, calibrated only against
            # noise. It makes the night alarm big-animal-only. The CSV and
            # COLLECT=top keep running regardless.
            #
            # CORRECTED 4 SEP 2026. This paragraph used to say that Talamati
            # had produced confirmed DAYLIGHT animals but STILL NO CONFIRMED
            # NIGHT ANIMAL. That is false. TWO CONFIRMED NIGHT ELEPHANTS exist:
            # 30 Aug 18:31:50 and 18:32:14 UTC on p9, and 3 Sep 18:32:53 UTC on
            # p41 (domed head, ear held out, trunk over the rim, tusk visible,
            # about 15 x 10 blocks and 90-110 filled, so it CLEARS BLOB_MIN 90).
            # Not one of the three rows measures its elephant: every logged box
            # is an illumination band or a pool of floodlit ground with the
            # animal outside or inside it by accident. So the floor here is
            # still uncalibrated against an animal, which is the original
            # point, but the premise "there has never been one" is retired.
            #
            # Re-checked 1 Sep 2026 against a second full night: 8 hits in 467
            # frames, all 8 archived and looked at, all 8 out-of-focus insects
            # and moths on or near the dome (blob 120 to 272, fill 0.44-0.75,
            # all compact, so neither the aspect ceiling nor bpk separates
            # them). No threshold in this file can tell them from an animal.
            # bsat should, and was rewritten on 1 Sep to measure at source
            # resolution; wait for a night of the corrected column before
            # touching anything here.
            "BLOB_MIN":  90,
            "DOM_MIN":   0.40,
            "FILL_CMP":  0.36,
            # The two brightest presets go into an overexposed blowout at
            # night, and the blowout edge is a tall solid bar: 6x23 blocks at
            # fill 0.77 on 30 Aug. 0.80 rejects it. UNMEASURED against any real
            # animal, because Talamati still has none.
            "FILL_WIDE": 0.80,
            "DIST_MAX":  6.0,
            "NB_MAX":    25,
        },
    },
    {
        # ADDED 2 SEP 2026. THIRD CAMERA, AND EVERY NUMBER BELOW IS BORROWED.
        #
        # URL confirmed 2 Sep 2026 from the SANParks page for this cam
        # (https://www.sanparks.org/travel/webcams/still/satara), which carries
        # the image as hibiscus.sanparks.org/webcams/satara.jpg. Same host and
        # same filename pattern as the other two, so curl_cffi with
        # impersonate=chrome should reach it; that is an inference from the
        # host, not a measured fetch.
        #
        # WHAT IS ACTUALLY KNOWN ABOUT THE SCENE, UPDATED 3 SEP 2026.
        # The block below used to say "nothing, not one frame has been
        # fetched". That is no longer true. From 861 rows of 2/3 Sep and two
        # archived daylight frames:
        #   - It IS lit at night. bright median 48.8, px median 2330.
        #   - It DOES pan, and widely: dist plateaus at 9-13 on presets with
        #     200+ frames, which is a sweep, not noise.
        #   - Daylight is very busy. nblobs median 129 against Nossob's 38 and
        #     Talamati's 55, px median 38783 of ~75k visible.
        #   - Two archived frames: a long straight concrete water channel with
        #     algae, open bush behind. Small birds on the rim measure about 4
        #     blocks each, far below any usable BLOB_MIN.
        # STILL UNKNOWN: natural blob sizes on a converged background, because
        # no Satara background has ever converged. Every blob statistic this
        # camera has produced is a background-mismatch statistic. Do not quote
        # any of them as a measurement of the scene.
        #
        # SO THE THRESHOLDS ARE TALAMATI'S, COPIED VERBATIM. That is a
        # deliberate choice, not laziness: Talamati's numbers were measured
        # against 693 real Kruger night frames and 906 mixed frames, so they
        # are the best available prior for a Kruger PTZ cam. They are NOT
        # measurements of Satara and nothing here may be quoted as one.
        #
        # IT IS DEAF ON PURPOSE. BLOB_MIN 90 at night and 60 in daylight makes
        # this a big-animal-only alarm, which for an uncalibrated camera is the
        # right trade: a quiet log beats a log that is 20% noise, and the
        # frames worth looking at come from COLLECT=top archiving the largest
        # blobs regardless of whether anything scores a hit.
        #
        # THE FIRST 24 HOURS DECIDE THREE THINGS, in this order:
        #   1. SIG_TOL. ANSWERED 3 SEP 2026, see the SIG_TOL entry below.
        #   2. BLOB_MIN. Lower it the moment there is one confirmed animal, the
        #      same rule as Talamati. Not before.
        #   3. Whether night is lit at all. ANSWERED 3 SEP 2026: IT IS LIT.
        #      680 night rows of 2/3 Sep, `bright` median 48.8 (range 14.1 to
        #      178.9) against Nossob's 65.3 and Talamati's 106.2, and `px`
        #      median 2330 changed pixels. Not a black frame. The night
        #      thresholds are live and they matter.
        #
        # NOT DEPLOYED HERE, AND NOT BY OVERSIGHT: CY_MAX, BACT_MAX and
        # SAT_MAX. All three are fitted to Nossob's specific framing library
        # and floodlight and inherit as inert 1.01. Copying them to a camera
        # with zero confirmed animals would be fitting a gate to a negative set
        # with nothing to protect.
        "name":  "satara",
        "label": "Satara waterhole (Kruger)",
        "url":   "https://hibiscus.sanparks.org/webcams/satara.jpg",
        "tz":    2,
        "active": [(0, 24)],
        "night":  (18, 6),

        "thr": {
            # 25 -> 11 ON 3 SEP 2026. THE ONE DETECTION CHANGE OF THAT SESSION.
            # It applies to both modes: thr_night does not set SIG_TOL, so it
            # inherits this one. 11 is Nossob's value and DEFAULTS'.
            #
            # THE PROBLEM IS UPSTREAM OF EVERY THRESHOLD IN THIS BLOCK.
            # Measured on 861 Satara rows, 2 Sep 13:03 to 3 Sep 04:49 UTC:
            #   90% of the 181 daylight rows and 45% of the 680 night rows sit
            #   in the DEAD BAND, 6.0 < dist <= 25. Those frames are close
            #   enough to be ADMITTED to a preset (SIG_TOL 25) and too far to
            #   be JUDGED on it (DIST_MAX 6.0), so they can never score a hit,
            #   and line 593 of watch.py folds every one of them into the
            #   background anyway. The background becomes the average of a
            #   whole PTZ sweep.
            #
            # THE PRESETS DO NOT CONVERGE, AND THAT IS THE PROOF.
            #   p2, night, 280 frames: dist median by n-tercile 8.8, 9.3, 8.9.
            #   p0, day,   146 frames: 11.0, 10.0, 13.3. Getting worse.
            # Against Nossob at SIG_TOL 11 over the same hours:
            #   p14, night, 132 frames: 0.6, 0.6, 0.7, and 121 of 132 under 2.
            # A converged preset sits under 2. These sit at 9 to 13 forever.
            # The distance histograms are broad and unimodal, not bimodal, so
            # this is not two clean views lumped together: it is one preset
            # whose signature walks the sweep, because line 540 drags it 0.3
            # toward every frame that matches.
            #
            # SEVEN PRESETS IN TWO DAYS. Satara created ids 0-6 and no more,
            # while Nossob at SIG_TOL 11 creates about 25 a day. The trigger
            # written here on 2 Sep ("if the preset count settles low ... come
            # down toward Nossob's 11") is met.
            #
            # WHAT IT COSTS, HONESTLY. Nothing measurable at the time.
            #
            # CORRECTED 4 SEP 2026. This paragraph used to say that Satara had
            # scored two hits in its whole life and that BOTH WERE CONFIRMED
            # FALSE POSITIVES. That is false and it was false when written.
            # BOTH ARE ANIMALS: an AFRICAN WILD CAT at 04 01:25:18 UTC (p4,
            # blob 109, box on the reflection) and a SPOTTED HYENA at
            # 04 02:03:18 UTC (p4, blob 359, box on part of the animal and all
            # of its reflection). Neither row measures its animal cleanly, so
            # neither may tune anything, but the camera is not sterile and no
            # argument here may lean on "nothing to lose" again.
            #
            # Opening NB_MAX changes
            # nothing here either - replayed on the 181 daylight rows, NB_MAX
            # 25/40/60/80/120/200 all give 0 hits, because DIST_MAX rejects 158
            # of 181 first. No threshold in this block can do anything until
            # the backgrounds converge.
            #
            # WHAT IT RISKS. More presets, each deaf for its first MIN_N 6
            # frames, and faster arrival at PRESET_CAP 120. That is designed
            # behaviour (least-recently-seen eviction, logged) and the cap was
            # raised to 120 for exactly this. Estimated, NOT measured: if the
            # sweep splits the way Nossob's does, expect 30-60 new ids a day
            # and MIN_N rejections up from 14 a night to perhaps 60-100.
            #
            # 11 IS BORROWED FROM NOSSOB, NOT MEASURED ON SATARA. The
            # fingerprints are not in the CSV, so the split cannot be simulated
            # without re-fetching the frames. The number to check tomorrow is
            # NOT the hit count. It is the dead-band share and the dist
            # tercile trend on the largest preset. If dist still plateaus above
            # 6, 11 is still too loose and the next stop is DIST_MAX itself.
            #
            # TALAMATI IS DELIBERATELY NOT CHANGED WITH IT. It has the same
            # disease (48% of night rows in the dead band; p92, 236 frames,
            # dist 12.3 / 12.0 / 11.8) but it has confirmed daylight animals
            # and one confirmed night elephant, so it has something to lose.
            # Satara has nothing, which makes it the free test bed. If this
            # works at Satara, Talamati follows next session on evidence
            # instead of on inference.
            #
            # EXISTING STATE LINGERS. The smeared p0 and p2 backgrounds are in
            # the Actions cache and will keep capturing whatever falls within
            # 11 of them until PRESET_TTL (7 days) or eviction retires them.
            # Expect the dead-band share to fall over days, not in one run.
            "SIG_TOL":   11,
            "PIX_THR":   24,
            "MIN_N":     6,
            "DOM_MIN":   0.0,
            "BLOB_MIN":  60,
            "BLOB_MAX":  900,
            "ASP_MAX":   2.2,
            # 0.44 -> 0.26 AND 25 -> 250, 4 SEP 2026 EVENING. ONE CHANGE IN TWO
            # KEYS, authorised by Jeremy as an explicit exception to the
            # one-change-per-session rule.
            #
            # THIS IS THE CAMERA THE PAIR WAS MEASURED ON. 650 Satara daylight
            # rows of 4 Sep, scored against the two frames whose box is
            # demonstrably on a bird (04 06:49:01 p12, blob 116, fill 0.28,
            # nblobs 217; 04 06:21:10 p23, blob 112, fill 0.38, nblobs 200):
            #     live                    2 hits / 650   0 of 2 birds
            #     NB_MAX 250 alone        6 hits / 650   0 of 2 birds
            #     FILL_CMP 0.26 alone     2 hits / 650   0 of 2 birds
            #     BOTH                   52 hits / 650   2 of 2 birds
            # Each gate alone catches nothing. There is no signal in either
            # half to confound, which is the whole justification for taking
            # both at once.
            #
            # 250, NOT 200: the 06:49:01 bird row reads nblobs 217.
            # 0.26, NOT HIGHER: that same row reads fill 0.28.
            #
            # THE PRICE. 0.3% of daylight rows to 8.0%, about 52 hits a day at
            # this camera, every one archived. Almost none will be animals.
            # Filtering them is stage 2's job, not this file's.
            #
            # IT ALSO RECOVERS A KNOWN MISS: the three spotted hyenas of
            # 03 09:53:04 (p6, blob 239, fill 0.27, dom 0.21, dist 3.6, nblobs
            # 189, box on the adult) now pass every gate. They are promoted out
            # of KNOWN_MISSES into REAL_ANIMAL in selftest.py, so this pair of
            # values is now load-bearing on three Satara daylight animals.
            #
            # WHAT IS NOW THE BINDING GATE HERE, measured the same evening and
            # NOT acted on tonight: FILL_WIDE 0.72. The warthog boar of
            # 03 14:40:58 (aspect 2.8, fill 0.31) and the wildebeest-type
            # antelope of 03 13:01:28 (aspect 4.1, fill 0.29) both fall to the
            # wide branch and fail there. BLOB_MAX 900 is the binding gate on
            # the banded mongoose of 03 15:29:51 at blob 1487. Both are real
            # and both wait for the volume read of 5 Sep.
            #
            # NIGHT DOES NOT COPY THIS. thr_night below sets its own.
            "FILL_CMP":  0.26,
            "FILL_WIDE": 0.72,
            # 6.0 -> 8.0, 4 SEP 2026 LATE EVENING, IN STEP WITH TALAMATI.
            # Both Kruger cameras run the same daylight DIST_MAX, as they have
            # since Satara was added, and the row that forced the change is at
            # Talamati (03 10:22:08, four elephants, dist 7.6, now a
            # single-gate miss once NB_MAX and FILL_CMP opened).
            #
            # WHAT IT DOES HERE, HONESTLY: ONE HARNESS RECOVERY THAT IS NOT A
            # FIELD RECOVERY. The lying spotted hyena of 03 09:54:05 (p15, blob
            # 868, 54x31, fill 0.52, box on the animal, the clearest hyena
            # image in the project) sits at dist 6.5 and now clears every
            # geometric gate. IT IS STILL LOST IN THE FIELD, to MIN_N: preset
            # 15 was on its SECOND frame ever. It is deliberately NOT promoted
            # to REAL_ANIMAL in selftest.py for that reason, because the
            # harness scores every row at n=99 and would report a detection
            # that the detector would not make.
            #
            # NONE of the three confirmed Satara daylight animals in
            # REAL_ANIMAL needs this: they sit at dist 3.2, 4.5 and 3.6. It
            # buys volume here, not recall, and the volume is unmeasured under
            # the new NB_MAX and FILL_CMP. Under the old ones it was about 4
            # extra Satara hits a day.
            "DIST_MAX":  8.0,
            "NB_MAX":    250,
        },

        # NIGHT IS UNTOUCHED BY THE 4 SEP EVENING BUNDLE, on purpose. Satara
        # night is not stopped by NB_MAX or by the fill floor: it is stopped by
        # PIX_THR 26 against a low-contrast IR scene. Night px median is 27 of
        # about 75,000 visible pixels and blob is exactly 0 on 57.4% of night
        # rows, and the 03 22:49:03 quadruped (visible to the eye at about
        # 9.6 x 6.4 blocks) logs px 49 and blob 2. No value of NB_MAX,
        # FILL_CMP, BLOB_MIN, DIST_MAX or DOM_MIN reaches that frame.
        "thr_night": {
            "PIX_THR":   26,
            "BLOB_MIN":  90,
            "DOM_MIN":   0.40,
            "FILL_CMP":  0.36,
            "FILL_WIDE": 0.80,
            "DIST_MAX":  6.0,
            "NB_MAX":    25,
        },
    },
]
