# sanparks-watch

Watches the SANParks Nossob and Talamati still cams and keeps only the frames
where something actually changed at the waterhole. Runs on GitHub's free
runners, so nothing has to stay open on your computer.
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
- the first line of the log should read `http stack: curl_cffi
  impersonate=chrome`. If it says `requests (no TLS impersonation)` the
  install failed and every frame will 403.

**4. Optional, phone alerts.** Install the free **ntfy** app, subscribe to a
hard-to-guess topic, then repo Settings > Secrets and variables > Actions >
New repository secret named `NTFY_TOPIC`. Without it the run still collects
everything, it just does not push. Recommended: leave it off until Nossob has
produced a real animal in `frames/`.

## Schedule

Cron is UTC, both parks are UTC+2.

    */5 * * * *             = round the clock

`cameras.py` gates each camera again with its own `active` hours, so widening
the cron alone changes nothing. Widen `active` too, or dispatch manually with
*force_all_hours* = `1`. Both were widened on 31 Aug 2026 to `[(0, 24)]`.
Daylight detection has still never been confirmed on a mammal, and a daylight
animal is far easier to identify by eye than a grey shape in IR, so the
daylight hours are the point of the change. The small hours come along for free
and should finally show when Nossob's generator gap falls.

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
`dom2`, `cx`, `cy`, `nblobs`, `blocks`, `vetoed` and `dist` for every single
frame, which is everything needed to retune without ever fetching an image
back. `cx`/`cy` are the blob centroid as fractions of the frame, and `dom2` is
dominance recomputed ignoring blobs of one or two blocks. Neither is used for
any decision yet; they are there to answer whether insects are what suppresses
`dom` on real animals. Retuning from
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
  cost of noise. Nossob day 45, Talamati day 60, Talamati night 45. Do **not**
  raise Nossob's night value: real night animals there measured 4 to 51 blocks,
  including an owl at 5 and a drinking jackal at 6.
- `DIST_MAX` / `NB_MAX` - the two gates added 31 Aug, see above.
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
(empty waterholes and injected targets) plus, since 31 Aug, 18 frames that were
archived and looked at by eye: 10 confirmed animals that must still be caught
and 8 confirmed empty frames that must still be rejected. It fails if the
false-positive count rises or detection drops.

## The two gates added on 31 Aug 2026

Both came out of 906 real logged frames, 30-31 Aug.

**`DIST_MAX`.** `SIG_TOL` decides which preset a frame *belongs to*. `DIST_MAX`
decides whether the match is close enough to *judge on*. They are deliberately
different numbers. At Talamati, `SIG_TOL` had to go to 25 to stop the PTZ
learning the same view three times, but that also lumps framings up to 25 apart
into one preset, and diffing a frame against a background it does not really
match produces enormous spurious change: the median changed-pixel count climbs
from 183 (dist 0-3) to 26908 (dist 18-25). Judging only frames within 6 removed
30 of Talamati's 53 hits and cost no confirmed Nossob animal.

**`NB_MAX`.** Every confirmed animal so far fragmented the change into at most
17 blobs (the dove flock; the night animals ran 1 to 12). The four confirmed
Nossob dawn false positives scored 48, 52, 103 and 141. Diffuse illumination
change breaks into many pieces, an animal does not.

## Nossob's worst hour is dawn

Between roughly 06:00 and 08:00 local the sun comes up **and** the camera swaps
its IR-cut filter in, so it goes from greyscale to colour. Every preset
background is stale at the same moment. Measured 31 Aug on preset 3, one view,
90 minutes: blob 344, 308, 290, 220, then 66, then 26 as the background caught
up. Four of those frames scored hits with nothing in them. `NB_MAX` rejects all
four. Do not try to fix this by raising `BLOB_MIN`.

## Known gaps

- **Talamati has still never produced a confirmed true positive.** Nossob has
  ten confirmed animal frames (doves, jackals, an owl).
- **Daylight is confirmed only on birds.** The 30 Aug dove flock is the only
  real daylight detection. Gemsbok and elephant sensitivity is still synthetic
  only, which is why the schedule now covers the whole day.
- **Insects cannot be told from a distant small animal in the CSV.** At Nossob
  after dark a floodlit insect and a drinking jackal both land at 3-6 blocks
  with high fill and high dominance. `dom2`, `cx` and `cy` are now logged to
  attack this; nothing decides on them yet.
- **Nossob's nightly generator gap is uncharacterised.**
- **A jackal in daylight is not detectable** by this pipeline on either camera.
  Night is where the small-animal sensitivity lives.
- **Repo growth.** Round the clock at 5-minute cron is 288 runs a day. At
  `TOP_N=1` that is roughly 290 archived frames per camera per day, about
  60 MB, because a daylight JPEG archives at ~150 KB against ~55 KB at night.
  Prune `frames/` periodically, or drop `COLLECT` to `hits` once the insect
  question is settled and the archive is no longer earning its keep.
