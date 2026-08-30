# sanparks-watch

Watches the SANParks Nossob and Talamati still cams and keeps only the frames
where something actually changed at the waterhole. Runs on GitHub's free
runners, so nothing has to stay open on your computer.

```
watch.py                     the detector, camera-agnostic
cameras.py                   the camera list and every threshold
selftest.py                  replays real measured frames through the rule
.github/workflows/watch.yml  scheduled runner
```

## Why this is not "diff the last two frames"

**Both cameras pan between fixed presets.** Consecutive frames are usually
different views, so a plain frame difference fires on 100% of frames. Each
frame is fingerprinted (16x9 brightness-normalised thumbnail), matched to its
preset, and diffed only against that preset's own background.

**Brightness drifts constantly.** Floodlight and night gain at Nossob, moving
sun at Talamati. Every frame is brightness normalised before comparison.

**The remaining false alarms have a shape.** So the decision is made on the
largest connected blob of change and its geometry, not on a pixel count.

**Parts of the scene never stop moving.** Each preset also learns which blocks
change in almost every frame (grass, foliage) and takes them out of the
decision once it has seen `ACT_MIN_N` frames of that view.

## The thing that will bite you: `dom` is a night rule

`DOM_MIN` says the largest blob must account for some share of all the change
in the frame. At Nossob after dark that is a great rule, because the floodlit
scene is nearly static and an animal really is most of the change.

**In daylight it is false on both cameras.** Measured 30 Aug 2026: every
daylight frame carries 100-500 changed blocks from wind, grass and moving sun.
Injecting animal-sized targets into real frames and real learned backgrounds,
`dom` never reached 0.45 - so with the night config, daylight detected nothing
at all, not even an elephant. The daylight configs therefore set `DOM_MIN` to
`0` and lean on blob size, solidity and the smear rejector instead.

If you ever "fix" daylight by raising `DOM_MIN`, you will get a beautifully
quiet log that can never detect anything. Run `selftest.py`.

## How the two cameras differ

Both were watched simultaneously for 30 minutes on 30 Aug 2026, 13:39-14:07 UTC.

| | Nossob | Talamati |
|---|---|---|
| Scene | open floodlit sand, wide sky | dense bush, tall grass, dappled sun |
| New image | ~2 per minute | ~2 per minute, dropping to 1 |
| Presets seen in 20 min | 8, converging | 13, still growing |
| Busiest preset revisits | 10 | 4 |
| Median changed pixels | 1.9k of 75k (2.5%) | 4.8k of 75k (6.4%) |
| Largest natural blob | 66 blocks converged, 268 still settling | 455 blocks |
| Injected gemsbok | 8/8 detected | 1/5 |
| Injected jackal | 0/8, daylight limit | 0/5 |
| Burnt-in clock lag | ~8 min behind `Last-Modified` | ~8 min, same |

The short version: Talamati is a harder camera in every dimension. It is
noisier, its PTZ sweeps wider and repeats less, and its natural blobs are
larger than an injected elephant. Its config is a **data-collection** setting,
not a working alarm.

## Setup

**1. Create the repo.** github.com > New repository, name it
`sanparks-watch`, set it **Public** (public = free unlimited Actions minutes).

**2. Upload the files.** Add file > Upload files, drag in `watch.py`,
`cameras.py`, `selftest.py`, `README.md`, `.gitignore`. Commit. The workflow
needs its folders, so use Add file > Create new file and type the path
`.github/workflows/watch.yml` (typing the slashes creates the folders), paste
the contents, commit.

**3. Test the connection before trusting a whole day.** Actions tab >
"I understand my workflows, go ahead and enable them" > sanparks-watch >
Run workflow, set *Seconds to poll* to `40`, leave *force_all_hours* at `1`,
Run. Read the log:

- lines like `[nossob] ... p0 n=1 px=... blob=...` mean it works.
- `*** 403 Forbidden ***` means Cloudflare blocks GitHub's IPs and this route
  is dead for that camera. This is still the single biggest untested risk.

**4. Optional, phone alerts.** Install the free **ntfy** app, subscribe to a
hard-to-guess topic, then repo Settings > Secrets and variables > Actions >
New repository secret named `NTFY_TOPIC`. Without it the run still collects
everything, it just does not push. Recommended: leave it off until Nossob has
produced a real animal in `frames/`.

## Schedule

Cron is UTC, both parks are UTC+2.

    */5 3-7,13-18 * * *     = 05:00-09:59 and 15:00-20:59 local

`cameras.py` gates each camera again with its own `active` hours, so widening
the cron alone changes nothing. Widen `active` too, or dispatch manually with
*force_all_hours* = `1`.

Each run polls for ~4.5 minutes and the 5-minute cron starts the next, so a
single run has to cover the gap itself. Both cameras are watched inside one
process on separate threads, which is deliberate: a matrix job per camera would
mean two runners pushing commits to the same repo every five minutes.

## What each run leaves behind

    logs/<cam>/YYYYMMDD.csv          every frame, every metric, ~200 bytes/frame
    frames/<cam>/YYYYMMDD/           the few most-changed frames per run
    hits/<cam>/YYYYMMDD/             full-resolution frames that passed the rule
    state/<cam>/                     preset backgrounds - NOT committed, see below

The CSV is the important one. It has `blob`, `bw`, `bh`, `fill`, `dom`,
`nblobs`, `blocks`, `vetoed` and `dist` for every single frame, which is
everything needed to retune without ever fetching an image back. Retuning from
a day of CSV is cheap; retuning from a day of JPEGs is not.

Archived frame names still sort by interest:

    frames/nossob/20260830/213004_p3_blob0059_f0.84.jpg
                          │      │  │         └ solidity of that blob
                          │      │  └ size of the largest blob of change
                          │      └ which camera preset
                          └ UTC time

`COLLECT` controls how much is kept: `top` (default, the `TOP_N` biggest blobs
per run plus every hit), `all` (every frame, ~40 MB per camera per night), or
`hits`.

### Why state is not committed

A preset background is 384x216 float16, about 166 KB. With 8-13 presets per
camera, committing state every five minutes would add hundreds of MB a day to
the repo. It lives in the Actions cache instead (`actions/cache`, restored by
prefix, saved per run). A cache miss costs one warm-up window, nothing more.

## Warm-up

A preset must be seen `MIN_N` times before it can report a hit, because its
background is still converging - the largest spurious blobs all come from
presets that have not settled. The activity veto needs `ACT_MIN_N` (12) frames
of the same view before it engages.

At Nossob that is roughly half an hour. **At Talamati it is hours**, because
13 presets share the same ~1 frame per minute, so any single view comes round
only every few minutes. Do not judge Talamati on its first hour.

## Tuning

Everything lives in `cameras.py`, split into `thr` (daylight) and `thr_night`.
Anything you leave out is inherited from `DEFAULTS` in `watch.py`.

- `BLOB_MIN` - the main daylight lever. Lower to catch smaller animals, at the
  cost of noise. Nossob day 45, Talamati day 60.
- `FILL_CMP` / `ASP_MAX` / `FILL_WIDE` - the smear rejector. If a herd lined up
  along the trough gets missed, raise `ASP_MAX` rather than lowering
  `FILL_WIDE`.
- `SIG_TOL` - how different two frames must be to count as separate presets.
  Talamati needs 25: its PTZ does not return to the same framing, and at 11 it
  was learning the same view three times over and starving every background of
  samples. Check `dist` in the CSV, and the preset count in the run summary.
- `DOM_MIN` - read the warning above before touching this.
- `ACT_MAX` / `ACT_MIN_N` - the activity veto. Lower `ACT_MAX` to suppress more
  scenery, at the risk of blanking a spot an animal actually stands in.

After any change: `python selftest.py`. It replays 38 real measured frames
(empty waterholes and injected targets) through the rule and fails if the
false-positive count rises or detection drops.

## Known gaps

- **No true positive has ever been measured on either camera.** Sensitivity is
  proven only against synthetic targets injected into real backgrounds.
- **The Cloudflare 403 question is still open.** Untested from GitHub runners.
  A `curl` from a cloud sandbox returned 403 in August.
- **Talamati at night is completely unknown.** It has never been watched after
  dark and it is not established whether the waterhole is even lit.
- **Nossob's nightly generator gap is uncharacterised.**
- **A jackal in daylight is not detectable** by this pipeline on either camera.
  Night is where the small-animal sensitivity lives.
