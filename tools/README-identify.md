# identify_test: does SpeciesNet see what the geometric detector misses?

Evaluation only. Read-only on this repo. Nothing here runs on a schedule,
nothing here commits, and nothing here imports `watch.py`, `cameras.py` or
`selftest.py`. Delete the files and the repo is exactly as it was.

**Revised 7 September 2026.** The harness now carries its own ground truth and
reports recall and false positives in the same table. The old instruction to
"score it against `animals.md`" is gone; that file does not exist.

## Run this first

Actions tab, `identify-test`, Run workflow, with the defaults:

    only   = animals
    limit  = 200

That is 200 of the 524 confirmed-animal frames. It finishes in minutes and the
summarise step prints **seconds per image on the runner**, which is the number
`state.md` open item 7 has been asking for over five sessions. Everything else
about scheduling stage 2 depends on it.

Once you have that number:

| what you want | `only` | `limit` | `offset` |
|---|---|---|---|
| the rest of the animals | `animals` | 0 | 200 |
| recall on everything confirmed | `animals` | 0 | 0 |
| the false-positive half | `empties` | 0 | 0 |
| one shard of the empties | `empties` | 1200 | 0, then 1200, 2400 |
| everything | `all` | 0 | 0 |

The empty set is 3,585 frames. At 2 s/image that is two hours, comfortably
inside `timeout-minutes` 350. At 6 s/image it is six hours and must be sharded.
The first run tells you which.

## What it does

Walks `hits/<cam>/<date>/*.jpg` and `frames/<cam>/<date>/*.jpg`, runs the
SpeciesNet ensemble (MegaDetector for the box, an EfficientNetV2-M classifier
for the species, geofenced to ZAF), and writes one CSV row per image joining
the model output to three things:

1. the metadata in the filename,
2. the logged CSV row for the same UTC second, so `logged_hit` says whether
   stage 1 fired,
3. the eye label in `tools/ground_truth.txt`.

## `tools/ground_truth.txt`

**524 archived frames that contain an animal, confirmed by eye over the whole
of `hits/` and `frames/` on 7 September 2026.** Any archived frame not listed
is a reviewed empty, which makes the file a negative set of 3,585 as well as a
positive set of 524. It is the only hand-maintained file here; add a line when
a new animal frame is confirmed.

Two things it does **not** say. It does not say the logged blob box is on the
animal: on the reviewed sample the box lands on the animal about 4 times in 16
at night and 2 times in 13 in Kruger daylight. And it does not carry a species,
which is one of the things this run exists to supply.

## Reading the output

Three blocks are printed to the Actions log and mirrored in
`identify_score.csv`.

**Stage 2 alone.** Recall on animal frames and firing rate on empty frames, per
camera and mode, at conf 0.1, 0.2 and 0.5. `md_animal_conf` is the maximum over
all detections labelled `animal`, not the top detection, because MegaDetector
sometimes ranks a spurious person or vehicle box above the animal.

**Stage 1 and stage 2 together**, a four-way split per camera, mode and label:

- `s2 only` on an **animal** row is an animal the geometric detector missed and
  SpeciesNet would have found. That is the recall case for wiring stage 2 in.
- `both` on an **empty** row is a false positive stage 2 does **not** filter.
  That is the number that decides whether opening the daylight gates is
  affordable, because the whole argument for accepting 137 to 350 hits a day is
  that stage 2 removes the empties.
- `s1 only` on an **empty** row is what stage 2 would clean up.

**What it calls the animals.** The species tally on confirmed-animal frames.
This is what turns 524 filenames into 524 species records, which is what the
tracker needs and what no threshold work can supply.

## Columns that matter

- `utc` joins to `logs/<cam>/<date>_<cam>.csv`.
- `sast` is true park local time (utc + 2h). Use this one.
- `burnt_in` is what the stamp on the frame should read (utc + 1h51m45s), so it
  is a cross-check, not a time. Blank for satara, whose burnt-in clock is not
  usable.
- `mode` is day or night on watch.py's own rule: local hour, tz +2, night 18 to
  06. Computed from the filename, so it is present even when no log row is.
- `label` is `animal` or `empty` from the ground truth.
- `logged_hit` is stage 1's verdict on the same frame.
- `logged_blob` is the blob size the geometric detector recorded.
- `md_bw_blocks` / `md_bh_blocks` / `md_area_blocks` are MegaDetector's box on
  the same 96 x 54 grid, so they compare directly against the logged blob box.
  This is the column that answers whether the logged blob lands on the animal.
- `prediction` is the ensemble's final answer after geofencing and rollup. It
  may be a higher taxon (`felidae`, `mammalia`, `animal`) rather than a species;
  that is deliberate and is the model declining to guess.

## The log parser

`load_logs` parses by field count, not by header, and prints how many rows it
realigned. **Do not replace it with `csv.DictReader`.** Three log files written
before the 4 September schema rotation contain rows wider than their own
header: `logs/nossob/20260831.csv` (18-column header, 958 rows of 23) and
`logs/nossob/20260901.csv` and `logs/talamati/20260901.csv` (23-column headers,
1,728 and 855 rows of 26). A header-driven parser misaligns every one of those
rows and puts `bytes` into `hit`.

## Kaggle credentials

Model weights come from Kaggle by default. If the run fails with an auth or 403
error at the weights download step, add two repo secrets from a free Kaggle
account (Settings, API, Create New Token):

    KAGGLE_USERNAME
    KAGGLE_KEY

They are already wired into the workflow. No other account is needed and
nothing costs money.
