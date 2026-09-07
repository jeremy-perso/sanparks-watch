# Stage 2 in production: `identify` and `prune`

Added 7 September 2026. Both are additive. Neither imports `watch.py`,
`cameras.py` or `selftest.py`, neither reads the threshold table, and deleting
`tools/identify.py`, `tools/prune.py` and the two workflows returns the repo to
exactly what it was. **No threshold was changed.**

## Why, in one table

Measured 7 September 2026 on 67 eye-confirmed mammal frames and 3,702
eye-confirmed empty frames.

| | mammal frames | bird frames |
|---|---|---|
| total | 67 | 187 |
| the geometric detector catches | **20 (30%)** | 40 (21%) |
| SpeciesNet catches at conf 0.2 | **62 (93%)** | 175 (94%) |
| neither | 5 | 12 |

The five mammals both stages miss are marginal by eye: a whole-frame impala, two
elephants showing only an ear behind the dam wall, and two Satara night wild
cats. Every proposed gate change together takes the detector from 17 of 63 to 29
of 63 on mammals, at roughly 500 extra hits a day. **Stage 2 reaches 62 for
about 10 minutes of runner time.**

## `identify`

Scheduled daily at 02:40 UTC, 04:40 local, and dispatchable. It lists archived
hits that have no species row yet, scores them, and writes
`species/<cam>/YYYYMMDD.csv`, one row per frame. Then it commits `species/` and
nothing else.

**Idempotent by UTC second.** A frame already in the log is never re-scored, so
a re-run after a failed job costs only the frames that were missed. The model is
deterministic on CPU, verified over two runs of the same 200 images, so a
re-score would return the same answer anyway.

**The list is newest first and capped at `max_images` 600.** A cap can leave a
backlog, and the run says so, but it can never leave last night waiting behind
August.

**Cost.** 2.75 to 3.64 s/image over three measured runs on the standard CPU
runner. About 200 hits a day is 10 to 12 minutes. Warm caches add ~70 s of
setup; cold they add 13 minutes for the 214 MB weights and the pip install.

### The threshold is per mode: 0.30 daylight, 0.15 night

Decided with Jeremy 7 September, against the 223-frame priority set and the
3,702 eye-confirmed empties:

| | priority kept | empties retained |
|---|---|---|
| flat 0.30 | 193/223 | 646/3,702 |
| **0.15 night, 0.30 daylight** | **207/223** | **760/3,702** |

**Night is cheap and daylight is not, which is the whole reason for the split.**
0.30 to 0.15 at night costs 53 extra retained empties at Nossob night, 25 at
Satara and 24 at Talamati. The same move in daylight would cost 133, 79 and 157
for nothing: daylight priority recall is already 18/18, 10/10 and 31/31 at 0.30.

**Reverting needs no re-scoring.** Every run prints a THRESHOLD WATCH block
giving what 0.15, 0.20, 0.30 and 0.50 would each have kept, per camera and mode.
If the night archive grows faster than it is worth, raise `keep_conf_night` in
the workflow inputs and leave daylight alone. Note that the Satara wild cat of
04 01:47:52 sits at conf 0.151, so **0.20 loses it**.

Mammal recall is flat from conf 0.10 to 0.50: 64, 62, 62, 61 of 67, so the
threshold costs nothing in mammals at any of these settings. Firing rate on the
3,702 confirmed-empty frames:

| conf | nossob day | nossob night | satara day | satara night | talamati day | talamati night |
|---|---|---|---|---|---|---|
| 0.20 | 62% | 10% | 40% | 21% | 30% | 5% |
| **0.30** | **49%** | **7%** | **29%** | **14%** | **17%** | **3%** |
| 0.50 | 28% | 2% | 14% | 8% | 4% | 1% |

**Above 0.70 mammal recall breaks to 54 of 67 and it must not be used.**

### Reading `species/<cam>/<date>.csv`

`utc` joins to `logs/<cam>/<date>.csv`. `sast` is true park local time, +2h, and
is the column to read as a human. `md_animal_conf` is the score. `keep` is
`md_animal_conf >= keep_conf`, and `keep_conf` is written into every row, so a
row always says what it was judged against even after the setting changes.

**`keep=1` means stage 2 saw an animal. It is not a species identification.** On
small birds the classifier routinely returns `animal` or `blank` while
MegaDetector's box is confidently on the bird.

**Score on `md_animal_conf`, never on `prediction`.** The ensemble rolls up to
`blank` whenever the classifier has no confident label, including on 31 of 54
frames measured 7 September that carried an `animal` box at conf >= 0.2.
`md_animal_conf` is the maximum over all detections labelled `animal`, not the
top one, because a spurious person or vehicle box sometimes outranks it.

## `prune`

Manual dispatch only, **dry run by default**. It deletes an archived frame only
when all four hold: older than `keep_days` (21), stage 2 scored it `keep=0`, it
is not in `tools/ground_truth.txt`, and it has a species row at all. **An
unscored frame is never deleted**; run `identify` first.

The deletion list, and with `stage_files=true` the JPEGs themselves, upload as
an artifact with 90 days of retention **before** anything is removed. Git history
holds them forever regardless.

**Why deleting helps at all.** `watch.yml` checks out with `fetch-depth 1`, so
the checkout downloads the current tree, not the history. Removing an old JPEG
cuts checkout time immediately even though the blob stays in history. Repository
storage keeps growing; storage does not cost coverage, checkout does, and
checkout overhead is what erodes the duty cycle.

**Run it dry and read the artifact before ever setting `apply=true`.**

## Order of operations tonight

1. Upload this bundle. Nothing runs on a schedule until 02:40 UTC.
2. Dispatch `identify` once by hand with `max_images` 2000 to clear the backlog
   of already-archived hits. That is roughly 2 hours; the 90-minute timeout will
   cut it, which is harmless because the job is idempotent, so dispatch it twice.
3. Let the schedule take over. Check `species/` has a file per camera per day.
4. Leave `prune` alone for three weeks. Nothing is older than `keep_days` 21
   until the archive is, and by then there will be scores on everything.
5. Read the THRESHOLD WATCH block in the first few runs. It is the agreed
   mechanism for deciding whether night 0.15 is affordable.
