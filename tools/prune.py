#!/usr/bin/env python3
"""
prune.py

Retention for the archive, driven by the stage 2 score rather than by age
alone. Deletes nothing unless --apply is passed.

    python tools/prune.py                 # dry run, prints what it would do
    python tools/prune.py --apply         # actually deletes from the tree

WHY PRUNING WORKS AT ALL. `watch.yml` uses `actions/checkout@v4` with no
`fetch-depth`, so the checkout is shallow: it downloads the CURRENT TREE, not
the history. Deleting an old JPEG therefore cuts checkout time immediately even
though the blob stays in git history forever. Repository storage keeps growing;
storage does not cost coverage, checkout does. That is the mechanism behind
"coverage decays on its own" and this job is what stops it.

WHAT IT KEEPS, in order of precedence:

  1. Anything younger than --keep-days. No exceptions, so a frame is never
     deleted before there has been a chance to look at it.
  2. Anything stage 2 scored at or above the keep threshold, i.e. `keep=1` in
     species/<cam>/<date>.csv. These are the detections and they are kept
     indefinitely.
  3. Anything listed in tools/ground_truth.txt or tools/priority.txt. The 524
     ground-truth frames are the project's only eye-confirmed positive set and
     deleting one would silently break `selftest.py` and every recall figure in
     `measured-rows.md`. The 223 priority frames are the subset Jeremy sorted
     as worth detecting, and they are the recall target everything is now
     measured against.
  4. Anything with NO species row at all. An unscored frame is not a
     low-scoring frame. Run tools/identify.py first; until then this job
     leaves it alone.

Everything else is a frame older than --keep-days that stage 2 looked at and
scored below threshold. That is the class this job removes.

THE ARTIFACT IS THE SAFETY NET. The workflow uploads the deletion list before
deleting, and can upload the JPEGs themselves with --stage. Retention on that
artifact is 90 days, so a mistake is recoverable for three months. Git history
holds them forever regardless, since a shallow checkout does not fetch it.
"""

import argparse, csv, glob, os, re, shutil, sys
from datetime import datetime, timedelta, timezone

NAME_RE = re.compile(r"^(?P<hh>\d{6})_p\d+_blob\d+(?:_f[0-9.]+)?\.jpe?g$", re.I)


def load_keys(path):
    keys = set()
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                keys.add(line.replace("\\", "/"))
    return keys


def load_scores(root="species"):
    """(cam, 'YYYYMMDD', 'HHMMSS') -> keep flag as int."""
    out = {}
    for f in glob.glob(os.path.join(root, "*", "*.csv")):
        cam = os.path.basename(os.path.dirname(f))
        try:
            for r in csv.DictReader(open(f, newline="", encoding="utf-8")):
                u = r.get("utc", "")
                if len(u) < 19:
                    continue
                day = u[:4] + u[5:7] + u[8:10]
                hh = u[11:13] + u[14:16] + u[17:19]
                out[(cam, day, hh)] = int(r.get("keep", 0) or 0)
        except OSError:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", default="hits,frames")
    ap.add_argument("--cameras", default="nossob,talamati,satara")
    ap.add_argument("--keep-days", type=int, default=21)
    ap.add_argument("--species", default="species")
    ap.add_argument("--labels", default=os.path.join("tools", "ground_truth.txt"))
    ap.add_argument("--priority", default=os.path.join("tools", "priority.txt"))
    ap.add_argument("--list-out", default="pruned.txt")
    ap.add_argument("--stage", default="",
                    help="copy the doomed JPEGs here before deleting")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=a.keep_days)).strftime("%Y%m%d")
    scores = load_scores(a.species)
    labels = load_keys(a.labels) | load_keys(a.priority)
    print(f"cutoff {cutoff} (keep-days {a.keep_days}), "
          f"{len(scores)} scored frames, {len(labels)} protected frames "
          f"(ground truth plus priority)")

    doomed, stats = [], dict(total=0, young=0, keep=0, protected=0, unscored=0)
    for root in [r.strip() for r in a.roots.split(",") if r.strip()]:
        for cam in [c.strip() for c in a.cameras.split(",") if c.strip()]:
            base = os.path.join(root, cam)
            if not os.path.isdir(base):
                continue
            for day in sorted(os.listdir(base)):
                dd = os.path.join(base, day)
                if not (os.path.isdir(dd) and re.fullmatch(r"\d{8}", day)):
                    continue
                for nm in sorted(os.listdir(dd)):
                    m = NAME_RE.match(nm)
                    if not m:
                        continue
                    stats["total"] += 1
                    hh = m.group("hh")
                    if day >= cutoff:
                        stats["young"] += 1;      continue
                    if f"{cam}/{day}/{hh}" in labels:
                        stats["protected"] += 1;  continue
                    k = scores.get((cam, day, hh))
                    if k is None:
                        stats["unscored"] += 1;   continue
                    if k:
                        stats["keep"] += 1;       continue
                    doomed.append(os.path.join(dd, nm))

    bytes_ = sum(os.path.getsize(p) for p in doomed if os.path.exists(p))
    print(f"\narchived frames        {stats['total']}")
    print(f"  younger than cutoff  {stats['young']}")
    print(f"  stage 2 keep=1       {stats['keep']}")
    print(f"  protected           {stats['protected']}")
    print(f"  not scored yet       {stats['unscored']}  (left alone; run identify.py)")
    print(f"  DELETABLE            {len(doomed)}  ({bytes_/1e6:.0f} MB)")

    with open(a.list_out, "w", encoding="utf-8") as fp:
        for p in doomed:
            fp.write(p + "\n")
    print(f"\nlist -> {a.list_out}")

    if a.stage and doomed:
        for p in doomed:
            d = os.path.join(a.stage, p)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(p, d)
        print(f"staged {len(doomed)} files into {a.stage}/")

    if not a.apply:
        print("\nDRY RUN. Nothing deleted. Pass --apply to delete.")
        return 0

    for p in doomed:
        try:
            os.remove(p)
        except OSError as e:
            print(f"  could not delete {p}: {e}")
    print(f"\ndeleted {len(doomed)} files, about {bytes_/1e6:.0f} MB out of the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
