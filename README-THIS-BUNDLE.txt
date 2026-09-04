sanparks-watch-20260904a
========================
Built 4 September 2026, before dark.
Upload to GitHub, replacing:

  cameras.py   -> cameras.py
  watch.py     -> watch.py
  selftest.py  -> selftest.py

watch.yml and requirements.txt are UNCHANGED. Do not upload them.
TOP_N IS STILL 4 IN watch.yml AND THAT IS DELIBERATE. See note 5 below.

ONE DECISION CHANGE, THREE MEASUREMENT CHANGES, NOTHING ELSE.

1. cameras.py   talamati thr   SIG_TOL   25 -> 11
   THE ONLY THING IN THIS BUNDLE THAT CHANGES WHAT COUNTS AS A HIT.
   Proof it is needed: frames/talamati/20260903/183253_p41_blob0538_f0.38.jpg
   is the reservoir wall with a confirmed elephant. 183305_p41_blob0621_f0.31,
   logged TWELVE SECONDS LATER UNDER THE SAME PRESET ID, is a marula trunk over
   open grass. `bright` splits p41's 291 rows into 96 wall (107-118) and 195
   grass (84-96) with FOUR rows in the whole 98-105 band.
   Proof 11 splits it: `dist` IS the signature match distance (watch.py sets
   m["dist"] = bd, and bd is what SIG_TOL gates). 69.8% of p41's rows have
   dist > 11. Every one forks at 11.
   Cost: 23.2% of all Talamati rows fork on the first pass. The two cameras
   already at 11 sit at 0.0% (nossob) and 2.6% (satara) after converging.
   Buys: Talamati's dead band is 41% of daylight rows and 46% of night rows.
   At Satara the same change took the dead band from 90% to 11%.

2. watch.py     PRESET_CAP     120 -> 200
   INSURANCE FOR (1), NOT A FIX. Talamati already reached preset id 127 in 29
   hours at SIG_TOL 25; forking 23% of frames would risk evicting load-bearing
   presets mid-experiment. Cache cost ~66 MB vs ~40 MB per camera.

3. watch.py     three new CSV columns: dist2, pxlo, edge
   NO DECISION READS ANY OF THEM. is_hit is untouched. Each answers an open
   question that cannot be answered by replaying the existing log:
     pxlo   px at PIX_THR_LO 12 instead of PIX_THR 24. Satara night logs px
            median 27 and blob 0 in 57% of rows, and 224903_p3 shows an animal
            at px 49 / blob 2. Read pxlo/px on Satara night.
     edge   mean absolute horizontal gradient. 013209_p38 was captured mid-pan:
            n=2, px 14,419, nblobs 130, a preset minted and never seen again.
            Read `edge` against the preset's own median.
     dist2  distance to the SECOND-best preset. dist2 - dist is the margin, and
            it is the number that says whether SIG_TOL 11 split real views or
            minted duplicates. THIS IS HOW TO DECIDE WHETHER TO KEEP 11.

4. watch.py     CSV schema rotation
   Three columns went in mid-day, so today's 26-column file would have made
   DictWriter raise. If the header on disk does not match CSV_COLS the log
   rolls to {day}_{cam}_v2.csv. Old files are left untouched. Expect three new
   _v2.csv files today; that is correct behaviour, not a fault.

5. watch.yml    TOP_N left at 4 ON PURPOSE, and this is a decision to confirm.
   The revert has been carried as an action item since 3 Sep. It should not go
   in tonight: TOP_N 4 is the channel that produced every animal of the last
   two sessions, and tonight is the first night after a preset change at
   Talamati. At 1 there is one archived frame per run per camera and no way to
   see what the new presets are looking at. Cost is roughly 50 MB/day of JPEG
   into git history that can never be reclaimed. Revert it once identify is
   banding, or sooner if repo size bites.

SELFTEST, live config, BEFORE and AFTER this bundle:
   nossob night animals        51/53   ->  51/53
   nossob day animals            2/5   ->    2/5
   nossob day false pos         0/18   ->   0/18
   nossob night false pos        0/7   ->    0/7
   talamati day false pos       0/13   ->   0/13
   nossob day leaks             0/4    ->    0/4   (cap 0)
   nossob night leaks          43/81   ->  43/81   (cap 43)
   talamati night leaks         8/21   ->   8/25   (cap 8, DENOMINATOR GREW)
   satara night leaks          (new)   ->    0/1   (cap 0)
   injected GEOMETRY          8/8, 5/5 ->  unchanged
   injected FIELD             0/8, 0/5 ->  unchanged
   KNOWN MISSES               (new)    ->  0/10 caught
"all checks passed", exit 0.

NOTHING TRADED. The Talamati SIG_TOL change does not appear in these numbers at
all, because selftest scores rows and SIG_TOL decides which preset a row lands
in. That is a real limit of the harness and it is why (3) exists.

selftest.py also gains a KNOWN MISSES section: ten confirmed animals with CSV
rows that the live config misses, PRINTED EVERY RUN with the gate that stops
each one, and ASSERTED ON NOTHING. Adding them to REAL_ANIMAL would turn the
suite red until a recall-first config lands, and a permanently red suite stops
being read. Today it reports 0/10 and names DIST_MAX, NB_MAX and BLOB_MIN as
the gates. Any future config change now shows immediately which known animals
it recovers.

WHAT TO READ TOMORROW, in this order:
   1. share of Talamati rows with dist > 11. Falling toward Satara's 2.6% means
      it worked. Near 23% means the views are not separable by this fingerprint.
   2. p41. It should stop existing as one busy preset. Two new presets with
      bright clusters near 110 and near 93, each converging to dist < 3, is the
      whole hypothesis confirmed.
   3. dist2 - dist on Talamati. Wide margin = clean split. Narrow = duplicates.
   4. distinct preset ids per camera per day, against PRESET_CAP 200.
   5. pxlo/px on Satara night rows.
   6. edge, per preset, to size the mid-pan class.

WHAT IS DELIBERATELY NOT IN THIS BUNDLE:
   - Talamati daylight DIST_MAX 6.0 -> 8.0. It recovers NOTHING on its own: the
     one Talamati daylight row whose box is on the animals fails DIST_MAX at
     7.6 AND NB_MAX at 38 AND FILL_CMP at 0.28.
   - Any NB_MAX or FILL change at either Kruger camera. Recall there costs three
     gates or nothing, and three gates takes hits from 75/day to 181/day with
     every hit archived at full resolution. That waits for the identify job.
   - MIN_N. Five species have been lost to it, but changing it in the same
     bundle as SIG_TOL would confound the one measurement this deployment
     exists to make, since SIG_TOL 11 creates more new presets and every new
     preset is deaf for MIN_N frames.
   - A brightness term in the preset signature. MEASURED AND REJECTED: within-
     preset `bright` spread in daylight is 28 to 70 grey levels, far larger
     than the ~15 separating p41's two views. See the note in cameras.py.
