# identify_test: does SpeciesNet see what the geometric detector misses?

Evaluation only. Read-only on this repo. Nothing here runs on a schedule,
nothing here commits, and nothing here imports `watch.py`, `cameras.py` or
`selftest.py`. Delete the three files and the repo is exactly as it was.

## What it does

Walks `hits/<cam>/<date>/*.jpg` and `frames/<cam>/<date>/*.jpg`, runs the
SpeciesNet ensemble (MegaDetector for the box, an EfficientNetV2-M classifier
for the species, geofenced to ZAF), and writes one CSV row per image joining
the model output back to the metadata in the filename.

## How to run it

Actions tab, `identify-test`, Run workflow. Defaults scan everything.

Inputs worth knowing:

- `dates` blank scans all days. Set it to e.g. `20260901,20260902` to shard.
- `limit` / `offset` shard by count if a single run gets close to the 6h job cap.
- `country` defaults to `ZAF`, which cuts 2,498 labels to a plausible
  southern African set.

Output is an artifact called `identify-test-results` holding
`identify_test.csv`, the raw `predictions.json`, and the file list.

## Kaggle credentials

Model weights come from Kaggle by default. If the run fails with an auth or
403 error at the weights download step, add two repo secrets from a free
Kaggle account (Settings, API, Create New Token):

    KAGGLE_USERNAME
    KAGGLE_KEY

They are already wired into the workflow. No other account is needed and
nothing costs money.

## Columns that matter

- `utc` joins to `logs/<cam>/<date>.csv`.
- `sast` is true park local time (utc + 2h). Use this one.
- `burnt_in` is what the stamp on the frame should read (utc + 1h51m45s),
  so it is a cross-check, not a time. Blank for satara, whose burnt-in clock
  is not usable.
- `logged_blob` is the blob size the geometric detector recorded.
- `md_bw_blocks` / `md_bh_blocks` / `md_area_blocks` are MegaDetector's box
  expressed on the same 96 x 54 grid, so they compare directly against the
  logged blob box. This is the column that answers whether the logged blob
  lands on the animal.
- `prediction` is the ensemble's final answer after geofencing and rollup.
  It may be a higher taxon (`felidae`, `mammalia`, `animal`) rather than a
  species; that is deliberate and is the model declining to guess.

## What to do with the CSV

Score it against `animals.md`. The confirmed sets there are the eval set:
the 19 lion frames, the 15 jackal frames, the 5 barn owl frames, the
springbok, the hare, against the 58 Nossob night empty hits and the 10
Talamati night empty hits. Recall and false positives both, in the same
report.
