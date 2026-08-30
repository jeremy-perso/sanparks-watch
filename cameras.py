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
  talamati night - UNMEASURED. Never watched after dark. Starting point only.
"""

CAMERAS = [
    {
        "name":  "nossob",
        "label": "Nossob waterhole (Kgalagadi)",
        "url":   "https://hibiscus.sanparks.org/webcams/nossob.jpg",
        "tz":    2,                      # park local = UTC + this
        "active": [(5, 10), (15, 21)],   # local hours to watch, half-open
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
            "ASP_MAX":   2.4,
            "FILL_CMP":  0.32,
            "FILL_WIDE": 0.62,
        },
    },
    {
        "name":  "talamati",
        "label": "Talamati waterhole (Kruger)",
        "url":   "https://hibiscus.sanparks.org/webcams/talamati.jpg",
        "tz":    2,
        "active": [(5, 10), (15, 21)],
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
        },

        # UNMEASURED. Talamati has not been watched after dark at all, and it
        # is not known whether this waterhole is even lit. Sits between the
        # daytime numbers and Nossob's night ones purely as a starting point.
        # Retune from logs/talamati/*.csv before trusting anything here.
        "thr_night": {
            "PIX_THR":   26,
            "BLOB_MIN":  12,
            "DOM_MIN":   0.40,
            "FILL_CMP":  0.36,
            "FILL_WIDE": 0.62,
        },
    },
]
