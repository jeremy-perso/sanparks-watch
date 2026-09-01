# sanparks-watch

Watches the SANParks Nossob and Talamati still cams and keeps only the frames
where something actually changed at the waterhole. Runs on GitHub's free
runners, so nothing has to stay open on your computer.

As of 1 Sep 2026 it has caught a lion.

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

    */5 * * * *             = round the clock, RUNTIME 540

`cameras.py` gates each camera again with its own `active` hours, so widening
the cron alone changes nothing. Widen `active` too, or dispatch manually with
*force_all_hours* = `1`. Both were widened on 31 Aug 2026 to `[(0, 24)]`.
Daylight detection has still never been confirmed on a mammal, and a daylight
animal is far easier to identify by eye than a grey shape in IR, so the
daylight hours are the point of the change. The small hours come along for free
and should finally show when Nossob's generator gap falls.

**GitHub does not honour `*/5`.** Measured over both logs, 31 Aug 17:00 to
1 Sep 09:27 local: 67 run windows in 16h 27m, one every 14.7 minutes. Two
thirds of the scheduled events are simply dropped, and shortening the cron does
not help because five minutes is GitHub's documented floor anyway.

So `RUNTIME` is the coverage lever, not the cron. At 270 s inside a 882 s cycle
the detector was awake 31% of the time. It is now 540 s, about 61%, with
`timeout-minutes` 15 to match. Do not raise the timeout further: `concurrency`
has `cancel-in-progress: false`, so a hung job holds the queue for its whole
timeout.

Both cameras are watched inside one process on separate threads, which is
deliberate: a matrix job per camera would mean two runners pushing commits to
the same repo.

## What each run leaves behind

    logs/<cam>/YYYYMMDD.csv          every frame, every metric, ~200 bytes/frame
    frames/<cam>/YYYYMMDD/           the few most-changed frames per run
    hits/<cam>/YYYYMMDD/             full-resolution frames that passed the rule
    state/<cam>/                     preset backgrounds - NOT committed, see below

The CSV is the important one. It has `blob`, `bw`, `bh`, `fill`, `dom`,
`dom2`, `cx`, `cy`, `nblobs`, `blocks`, `vetoed` and `dist` for every single
frame, which is everything needed to retune without ever fetching an image
back. `cx`/`cy` are the blob centroid as fractions of the frame, and Retuning from a day of CSV is cheap; retuning from a day of
JPEGs is not.

The schema has changed twice and any analysis has to split on it:

| from | columns | added |
|---|---|---|
| start | 18 | |
| 31 Aug 12:48 UTC | 23 | `dom2` `cx` `cy` `bpk` `bsat` |
| 1 Sep bundle | 26 | `blob2` `bact` `veto30` |

`bpk` and `bsat` are **not comparable across the 1 Sep boundary**: they used to
be measured on the 384x216 analysis array and are now measured on the source
JPEG. See "The instrumentation" below.

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
  cost of noise. Nossob day 45, Talamati day 60, Talamati night 90. Do **not**
  raise Nossob's night value of 3. The 1 Sep lion measured **524 blocks on one
  preset and 3 on another in the same minute**; an owl measured 4 and a
  drinking jackal 6. Raising it to 4 would remove 20 of that night's 68 false
  positives and cost a lion frame and all the owl's margin. It is the cheapest
  remaining lever and it is still not worth it.
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
(empty waterholes and injected targets) plus 112 frames that were archived and
looked at by eye: 19 confirmed animals that must still be caught and 93
confirmed empty frames. `REAL_MIN` is a floor on detections and `FP_MAX` is a
ceiling on leaks, so the test fails if detection drops **or** the
false-positive count rises. Report both numbers whenever you change anything.

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

## The instrumentation, and two columns that were broken

`cx`/`cy`, `dom2`, `bpk` and `bsat` were added on 31 Aug as instruments, with
nothing deciding on them. A night of data later, two of the four were broken.

**`bsat` could never fire at Nossob, and the reason was a resize.** It was
computed on the 384x216 analysis array, which is a 5x downsample of a 1920x1080
JPEG. A saturated point source, an insect wing or an owl's eyeshine, averages
away completely. Measured 1 Sep on the 77 Nossob night hits: 31 contain source
pixels at 250 or above, and every one of them logged `bsat` 0.00. Talamati's
lens insects are big enough to survive the resize, which is why the same column
looked alive there (158 of 467 night frames) and dead at Nossob. It is now
measured on the source JPEG. **Values before and after 1 Sep are not
comparable.**

**`dom2` is broken by design and is kept only for continuity.** It divides by
the sum of blobs of 3 blocks or more, but a Nossob floodlit insect *is* 3 to 6
blocks, so the divisor collapses to the top blob alone and `dom2` pins at
exactly 1.00. Measured on 225 night frames with blob >= 3: 73% of the
3-to-5-block frames score exactly 1.00. Substituting it for `dom` admitted 23
extra insect-sized frames and dropped 23 animal-sized ones. Use **`blob2`**,
the second-largest blob, which is what `dom2` was reaching for.

**`bact` is the new one to watch.** It is the mean activity-veto score of the
blob's own blocks. `ACT_MAX` 0.60 vetoed something in 3 of 493 Nossob night
frames and in **zero of the 77 hits**, while about 35 of those hits were
swaying grass. Median changed blocks per night frame is 4 out of 5184, so no
block ever approaches 0.60. `bact` says what the grass actually scores, so
`ACT_MAX` can be set from data rather than guessed. `veto30` logs what
`ACT_MAX` 0.30 would have removed from each frame.

## Known gaps

- **Talamati has still never produced a confirmed NIGHT animal.** Its daylight
  true positives arrived 31 Aug (zebra, wildebeest, an elephant herd). Two full
  nights have now produced 8 hits, all of them out-of-focus insects on the
  dome, and no threshold in `cameras.py` can tell them from a large animal:
  they are big, bright and compact, which is exactly what an animal would be.
- **Nossob night runs at about 12% precision.** 9 animals in 77 hits on 31 Aug
  to 1 Sep, improving to 9 in 66 with the `FILL_WIDE` change. That is why
  `NTFY_TOPIC` is still deliberately unset.
- **Insects cannot be told from a distant small animal in the CSV.** At Nossob
  after dark a floodlit insect and a drinking jackal both land at 3-6 blocks
  with high fill and high dominance. The corrected `bsat` and `blob2` are the
  next attempt; nothing decides on them yet.
- **Nossob has no generator gap**, at least not one longer than a scheduling
  hole. Measured 31 Aug to 1 Sep: frames delivered in all 67 run windows, and
  no preset's brightness collapses. Every gap over 12 minutes appears at the
  identical timestamp in the Talamati log, so those are GitHub, not the camera.
- **A jackal in daylight is not detectable** by this pipeline on either camera.
  Night is where the small-animal sensitivity lives.
- **The day/night boundary is in the wrong place.** `night` is `(18, 6)`, but
  the sunrise runs entirely under day thresholds and dusk is still carrying
  5000 to 7500 changed pixels when the night config takes over. A fully lit
  colour frame with three doves in it at 17:57 burnt-in was classified `night`.
- **Repo growth.** GitHub actually delivers about 98 runs a day, not the 288
  the cron asks for. At `TOP_N=1` that is roughly 98 archived frames per camera
  per day, about 10 MB, because a daylight JPEG archives at ~150 KB against
  ~55 KB at night. Less than previously assumed.
