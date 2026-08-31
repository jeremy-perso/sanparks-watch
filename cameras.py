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
  nossob   night - 101 real night frames, 24 Aug 2026. 0 false positives.
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

        # The 24 Aug night calibration, untouched.
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
            "FILL_WIDE": 0.62,
            "NB_MAX":    25,
            "DIST_MAX":  6.0,
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
            # New-preset distances came in two clusters: 11.8, 11.9, 14.9,
            # 19.9, then nothing until 50.2. The low cluster is the same view
            # being learned twice - re-fingerprinting the saved frames put
            # those pairs 1.8-9.3 apart. 25 sits in the empty gap and stops the
            # fragmentation that was starving every background of samples.
            "SIG_TOL":   25,
            "PIX_THR":   24,     # the value all the numbers above were measured at
            "MIN_N":     6,      # backgrounds converge slower here
            "DOM_MIN":   0.0,
            "BLOB_MIN":  60,     # below this it is always vegetation
            "BLOB_MAX":  900,
            "ASP_MAX":   2.2,
            "FILL_CMP":  0.44,   # compact naturals measured 0.29 and 0.38
            "FILL_WIDE": 0.72,   # smear naturals measured 0.36-0.65
            # SIG_TOL 25 stopped the fragmentation but it also lumps framings
            # up to 25 apart into one preset, and a frame 15-25 from its own
            # background is not that view. All 7 daylight hits of 30-31 Aug sat
            # above dist 6 and none contained an animal.
            "DIST_MAX":  6.0,
            "NB_MAX":    25,
        },

        # NOW MEASURED, 226 night frames on 30-31 Aug 2026. Two findings.
        #
        # The waterhole IS lit: an IR floodlight, and the archived frames show
        # insects streaking through it exactly as at Nossob.
        #
        # The starting-point guess was far too loose. It fired on 46 of 226
        # frames (20%) and not one of the frames pulled back contained an
        # animal: they were insects, an overexposed blowout on the bright
        # presets, and preset 9 diffing against a smeared background. DIST_MAX
        # takes 30 of those, BLOB_MIN 45 takes most of the rest, leaving 11.
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
            # noise, because Talamati has still never produced a confirmed
            # animal. It makes the night alarm big-animal-only. The CSV and
            # COLLECT=top keep running regardless, and the frames worth
            # looking at here have always come from COLLECT=top rather than
            # from hits. Replace it with a gate on `bsat` as soon as there is
            # a night of that column to look at.
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
]
