#!/usr/bin/env python3
"""
identify.py

Stage 2 in production. Finds archived frames that have no species row yet,
hands them to SpeciesNet, and writes one row per frame to
`species/<cam>/YYYYMMDD.csv`.

    python tools/identify.py list   --out filepaths.txt
    python tools/identify.py record --predictions predictions.json

It touches no detector code and reads `cameras.py` not at all. Its only writes
are under `species/`.

THE THRESHOLD IS PER MODE: 0.30 in daylight, 0.15 at night. Measured 7
September 2026 against the 223-frame priority set (tools/priority.txt) and
3,702 eye-confirmed empty frames.

    flat 0.30 everywhere         priority 193/223   empties retained 646/3702
    0.15 night / 0.30 daylight   priority 207/223   empties retained 760/3702

**Night is cheap and daylight is not**, which is the whole reason for the split.
Going 0.30 -> 0.15 at night costs 53 extra retained empties at Nossob night, 25
at Satara night and 24 at Talamati night. The same move in daylight would cost
133 at Nossob, 79 at Satara and 157 at Talamati, for frames stage 2 already
catches at 0.30 anyway: daylight priority recall is 18/18, 10/10 and 31/31 at
either threshold.

WHAT 0.15 BUYS, concretely: 14 priority frames, 13 of them at Nossob night, plus
the Satara wild cat of 04 01:47:52 which MegaDetector boxes at the top edge of
the frame at conf 0.151. That row clears 0.15 by one thousandth. If the
threshold is ever raised to 0.20 that animal is lost again.

HOW TO REVERT, decided with Jeremy 7 September: run night at 0.15 and watch the
volume. Every run prints a THRESHOLD WATCH block giving the keep count this run
at 0.15, 0.20, 0.30 and 0.50 per camera and mode, so the cost of moving is
visible without re-scoring anything. Raise `keep_conf_night` in the workflow
inputs if the night archive grows faster than it is worth.

Mammal recall is FLAT from conf 0.10 to 0.50 (64, 62, 62, 61 of 67 eye-confirmed
mammal frames), so the threshold costs nothing in mammals at any of these
settings and everything in volume. Above 0.70 mammal recall breaks to 54 of 67
and it must not be used at all.

WHAT `keep` MEANS. `keep=1` is "stage 2 saw an animal at or above the threshold
for that frame's mode". The threshold used is written into the row as
`keep_conf`, so a row always says what it was judged against.
It is the flag `prune.py` reads, and nothing else depends on it. It is NOT a
species identification: on small birds the classifier routinely returns `animal`
or `blank` while MegaDetector's box is confidently on the bird.

SCORE ON `md_animal_conf`, NEVER ON `prediction`. The ensemble rolls up to
`blank` whenever the classifier has no confident label, including on 31 of 54
frames measured 7 September where MegaDetector had an `animal` box at conf
>= 0.2. `md_animal_conf` is the maximum over ALL detections labelled `animal`,
not the top one, because a spurious person or vehicle box sometimes outranks it.

IDEMPOTENT BY UTC. A frame whose UTC second already appears in
`species/<cam>/<date>.csv` is never re-scored, so a re-run after a failed job
costs only the frames that were missed. The model is deterministic on CPU
(verified 7 September: two runs over the same 200 images produced identical
`md_animal_conf` on every row), so a re-scored frame would give the same answer
anyway.
"""

import argparse, csv, glob, json, os, re, sys
from datetime import datetime, timedelta, timezone

KEEP_CONF_DAY = 0.30
KEEP_CONF_NIGHT = 0.15
GRID_W, GRID_H = 96, 54
TZ_HOURS, NIGHT_FROM, NIGHT_TO = 2, 18, 6

NAME_RE = re.compile(r"^(?P<hh>\d{6})_p(?P<preset>\d+)_blob(?P<blob>\d+)"
                     r"(?:_f(?P<fill>[0-9.]+))?\.jpe?g$", re.I)

COLS = ["utc", "sast", "cam", "mode", "preset", "source", "logged_blob",
        "md_animal_conf", "keep", "keep_conf",
        "prediction_common", "prediction_class",
        "prediction_score", "n_detections", "md_bw_blocks", "md_bh_blocks",
        "md_cx", "md_cy", "model_version", "path"]


def parse_path(path):
    parts = path.replace("\\", "/").split("/")
    m = NAME_RE.match(parts[-1]) if parts else None
    if not m or len(parts) < 4 or not re.fullmatch(r"\d{8}", parts[-2]):
        return None
    day, cam, source = parts[-2], parts[-3], parts[-4]
    # Repo-relative, because predictions.json carries the runner's absolute
    # path and a species log full of /home/runner/... is useless off the runner.
    rel = "/".join(parts[-4:])
    try:
        ts = datetime.strptime(day + m.group("hh"), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None
    local = (ts.hour + TZ_HOURS) % 24
    return dict(
        path=rel, cam=cam, day=day, source=source,
        utc=ts.strftime("%Y-%m-%d %H:%M:%S"),
        sast=(ts + timedelta(hours=TZ_HOURS)).strftime("%Y-%m-%d %H:%M:%S"),
        mode="night" if (local >= NIGHT_FROM or local < NIGHT_TO) else "day",
        preset=m.group("preset"),
        logged_blob=m.group("blob").lstrip("0") or "0")


def already_scored(root="species"):
    """(cam, utc) already written. Read every species CSV, tolerate none."""
    done = set()
    for f in glob.glob(os.path.join(root, "*", "*.csv")):
        cam = os.path.basename(os.path.dirname(f))
        try:
            for r in csv.DictReader(open(f, newline="", encoding="utf-8")):
                done.add((cam, r.get("utc", "")))
        except OSError:
            continue
    return done


def split_prediction(raw):
    """`<uuid>;<class>;...;<common>` -> (class, common)."""
    if not raw:
        return "", ""
    p = raw.split(";")
    return (p[1], p[-1]) if len(p) >= 7 else ("", raw)


def cmd_list(a):
    done = already_scored(a.species)
    dates = [d.strip() for d in a.dates.split(",") if d.strip()]
    found = []
    for root in [r.strip() for r in a.roots.split(",") if r.strip()]:
        for cam in [c.strip() for c in a.cameras.split(",") if c.strip()]:
            base = os.path.join(root, cam)
            if not os.path.isdir(base):
                continue
            for day in sorted(os.listdir(base)):
                if dates and day not in dates:
                    continue
                dd = os.path.join(base, day)
                if not os.path.isdir(dd):
                    continue
                for nm in sorted(os.listdir(dd)):
                    p = parse_path(os.path.join(dd, nm))
                    if p and (p["cam"], p["utc"]) not in done:
                        found.append(p)

    # ONE COPY PER INSTANT. Added 10 Sep 2026 with frames/ in the daily roots.
    # The run's TOP_N capture is often also a hit, so the same second exists as
    # the full-resolution hits/ JPEG and the 900 px frames/ copy. MegaDetector
    # gives different answers on the two (19 pairs measured 10 Sep), so scoring
    # both writes two conflicting rows for one UTC second. The hit wins.
    hit_keys = {(p["cam"], p["utc"]) for p in found if p["source"] == "hits"}
    n_all = len(found)
    found = [p for p in found
             if p["source"] == "hits" or (p["cam"], p["utc"]) not in hit_keys]
    twins = n_all - len(found)

    # Newest first, so a capped run always covers last night rather than
    # grinding through August again after a long outage.
    found.sort(key=lambda p: p["utc"], reverse=True)
    total = len(found)
    if a.max_images:
        found = found[:a.max_images]

    with open(a.out, "w", encoding="utf-8") as fp:
        for p in found:
            fp.write(os.path.abspath(p["path"]) + "\n")

    print(f"already scored:  {len(done)}")
    print(f"unscored frames: {total}")
    if twins:
        print(f"twins skipped:   {twins} frames/ copies of a second already listed as a hit")
    print(f"this run:        {len(found)}")
    if total > len(found):
        print(f"BACKLOG: {total - len(found)} frames left over. Raise "
              f"max_images or dispatch again; the list is newest-first so "
              f"nothing recent is waiting behind old frames.")
    by = {}
    for p in found:
        by[(p["cam"], p["mode"])] = by.get((p["cam"], p["mode"]), 0) + 1
    for k in sorted(by):
        print(f"  {k[0]} {k[1]}: {by[k]}")


def cmd_record(a):
    preds = json.load(open(a.predictions, encoding="utf-8")).get("predictions", [])
    rows_by_file = {}
    kept = 0
    for pr in preds:
        p = parse_path(pr.get("filepath", ""))
        if p is None:
            continue
        confs = []
        for d in (pr.get("detections") or []):
            if d.get("label") == "animal":
                try:
                    confs.append(float(d.get("conf", 0)))
                except (TypeError, ValueError):
                    pass
        conf = max(confs) if confs else 0.0
        kc = a.keep_conf_night if p["mode"] == "night" else a.keep_conf_day
        dets = pr.get("detections") or []
        d0 = dets[0] if dets else {}
        bbox = d0.get("bbox") or [0, 0, 0, 0]
        cls, common = split_prediction(pr.get("prediction", ""))
        row = {
            "utc": p["utc"], "sast": p["sast"], "cam": p["cam"],
            "mode": p["mode"], "preset": p["preset"], "source": p["source"],
            "logged_blob": p["logged_blob"],
            "md_animal_conf": round(conf, 4),
            "keep": 1 if conf >= kc else 0,
            "keep_conf": kc,
            "prediction_common": common, "prediction_class": cls,
            "prediction_score": pr.get("prediction_score", ""),
            "n_detections": len(dets),
            "md_bw_blocks": round(bbox[2] * GRID_W, 1) if dets else "",
            "md_bh_blocks": round(bbox[3] * GRID_H, 1) if dets else "",
            "md_cx": round(bbox[0] + bbox[2] / 2, 3) if dets else "",
            "md_cy": round(bbox[1] + bbox[3] / 2, 3) if dets else "",
            "model_version": pr.get("model_version", ""),
            "path": p["path"],
        }
        kept += row["keep"]
        rows_by_file.setdefault(
            os.path.join(a.species, p["cam"], p["day"] + ".csv"), []).append(row)

    written = 0
    for path, rows in sorted(rows_by_file.items()):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        seen = set()
        if os.path.exists(path):
            for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
                seen.add(r.get("utc", ""))
        new = [r for r in rows if r["utc"] not in seen]
        if not new:
            continue
        fresh = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=COLS, extrasaction="ignore")
            if fresh:
                w.writeheader()
            for r in sorted(new, key=lambda r: r["utc"]):
                w.writerow(r)
        written += len(new)
        print(f"  {path}  +{len(new)}")

    print(f"\nscored {len(preds)} frames, wrote {written} new rows, {kept} kept "
          f"(keep_conf {a.keep_conf_day} daylight, {a.keep_conf_night} night)")

    # THRESHOLD WATCH. The point of this block is that raising or lowering the
    # threshold never requires re-scoring anything: the cost of every candidate
    # is already in this run's output. Agreed with Jeremy 7 Sep 2026 when night
    # went to 0.15, so the decision to revert can be made from a log line.
    allrows = [r for rows in rows_by_file.values() for r in rows]
    if allrows:
        confs = {}
        for r in allrows:
            confs.setdefault((r["cam"], r["mode"]), []).append(r["md_animal_conf"])
        print("\n-- THRESHOLD WATCH: frames this run that would be kept --")
        print(f"  {'cam / mode':18}{'frames':>8}" +
              "".join(f"{t:>10}" for t in ("0.15", "0.20", "0.30", "0.50")))
        for k in sorted(confs):
            v = confs[k]
            line = f"  {k[0] + ' ' + k[1]:18}{len(v):8}"
            for t in (0.15, 0.20, 0.30, 0.50):
                line += f"{sum(1 for c in v if c >= t):10}"
            print(line + ("   <- night" if k[1] == "night" else ""))
        print("  Raise keep_conf_night in the workflow inputs if the night "
              "columns are running far above what is worth archiving.")

    tally = {}
    for rows in rows_by_file.values():
        for r in rows:
            if r["keep"]:
                k = (r["cam"], r["prediction_common"] or "(no label)")
                tally[k] = tally.get(k, 0) + 1
    if tally:
        print("\n-- what it saw, keep rows only --")
        for k, v in sorted(tally.items(), key=lambda kv: (kv[0][0], -kv[1])):
            print(f"  {k[0]:10}{v:5d}  {k[1]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list")
    p1.add_argument("--cameras", default="nossob,talamati,satara")
    p1.add_argument("--roots", default="hits")
    p1.add_argument("--dates", default="")
    p1.add_argument("--max-images", type=int, default=1000)
    p1.add_argument("--species", default="species")
    p1.add_argument("--out", default="filepaths.txt")
    p1.set_defaults(func=cmd_list)

    p2 = sub.add_parser("record")
    p2.add_argument("--predictions", default="predictions.json")
    p2.add_argument("--species", default="species")
    p2.add_argument("--keep-conf-day", type=float, default=KEEP_CONF_DAY)
    p2.add_argument("--keep-conf-night", type=float, default=KEEP_CONF_NIGHT)
    p2.set_defaults(func=cmd_record)

    a = ap.parse_args()
    a.func(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
