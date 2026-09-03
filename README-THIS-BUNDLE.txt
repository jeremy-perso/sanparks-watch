sanparks-watch-20260903c
========================
Upload to GitHub, replacing:

  cameras.py                        -> cameras.py
  selftest.py                       -> selftest.py
  .github/workflows/watch.yml       -> .github/workflows/watch.yml

watch.py and requirements.txt are UNCHANGED. Do not upload them.

THE THREE VALUE CHANGES (everything else in the diff is comment):

1. cameras.py  nossob thr_night  DIST_MAX  6.0 -> 8.0
   Recovers the confirmed lion group of 02 21:16:00 UTC (dist 7.2), a
   single-gate miss with the box on the animal. Costs 0 false positives on
   681 night rows. Night only; Nossob daylight and both Kruger cameras keep 6.0.

2. cameras.py  satara thr         SIG_TOL   25 -> 11
   Applies to both Satara modes (thr_night inherits it). 90% of Satara daylight
   rows and 45% of night rows were unjudgeable; its dominant presets have not
   converged in 280 samples.

3. .github/workflows/watch.yml     TOP_N     1 -> 4   (two places)
   *** REVERT BOTH TO 1 BEFORE DARK ON 3 SEP 2026. ***
   Roughly 50 MB of JPEG per full daylight day.

selftest.py, live config, before and after:
   nossob night animals    48/50  ->  51/53   (REAL_MIN raised 48 -> 51)
   nossob night leaks      43/81  ->  43/81   (cap 43, unchanged)
   talamati night leaks     8/21  ->   8/21   (cap 8, unchanged)
   nossob day false pos     0/18  ->   0/18
   nossob day animals        2/5  ->    2/5
   injected GEOMETRY         8/8, 5/5 unchanged
   injected FIELD          (new)  ->   0/8, 0/5
"all checks passed", exit 0.

Verified: reverting DIST_MAX to 6.0 makes selftest FAIL at 50/53 with
"missed: THREE LIONS drinking, 02 21:16:00Z". The threshold and the animal
that justifies it are tied together in the test.

SEPARATE, NO COMMIT NEEDED: dispatch one daylight run with
collect=all, runtime=540, force_all_hours=1. That is the unbiased sample.
Do not dispatch after dark: concurrency has cancel-in-progress: false.
