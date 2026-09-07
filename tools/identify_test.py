#!/usr/bin/env python3
"""
identify_test.py

Evaluation harness only. Reads the archived JPEGs, hands them to SpeciesNet,
and joins the result back to three things: the metadata in the filename, the
logged CSV row for that frame, and Jeremy's eye label from
`tools/ground_truth.txt`.

Writes nothing into the repo. Touches no detector code.

    python tools/identify_test.py list      --out filepaths.txt
    python tools/identify_test.py summarise --predictions predictions.json \
                                            --out identify_test.csv

REVISED 7 SEPTEMBER 2026. What changed and why:

  1. GROUND TRUTH IS NOW BAKED IN. `tools/ground_truth.txt` holds the 524
     archived frames Jeremy confirmed contain an animal, out of 4,109 archived.
     Every other archived frame was reviewed and is empty. So this harness can
     now report RECALL and FALSE POSITIVES in the same table instead of a bare
     tally of predictions. The old README said "score it against animals.md";
     that file no longer exists and the scoring is done here.

  2. THE LOG ROW IS JOINED IN. `logged_hit` says whether stage 1 fired on that
     frame, so the CSV answers the question the project actually has: what does
     stage 2 catch that stage 1 misses, and what would stage 2 throw away.

  3. THE LOG PARSER IS BY FIELD COUNT, NOT BY HEADER. Three log files written
     before the 4 September schema rotation carry rows wider than their own
     header: logs/nossob/20260831.csv (18-col header, 958 rows of 23),
     logs/nossob/20260901.csv and logs/talamati/20260901.csv (23-col header,
     1,728 and 855 rows of 26). csv.DictReader misaligns every one of those
     rows and puts `bytes` into `hit`. Do not replace this with DictReader.

  4. `md_animal_conf` IS THE MAXIMUM OVER ALL DETECTIONS, not the top one.
     Scoring on the first detection only understates recall whenever
     MegaDetector puts a person or vehicle box above the animal box.

  5. `prediction` IS SPLIT INTO READABLE COLUMNS. The raw field is a
     semicolon-joined string starting with a UUID
     (`ddf59264-...;mammalia;carnivora;felidae;panthera;leo;lion`), which is
     unreadable in a tally. `prediction_class` is the taxonomic class and
     `prediction_common` is the common name, and the printed summaries use
     them. The raw string is kept as `prediction` so nothing is lost.
     Added after the first real run, 7 September 2026.

  6. `--only animals` RUNS THE 524 POSITIVE FRAMES ALONE. Wall clock per image
     on the runner has been an open question for five sessions and nothing can
     be planned until it is measured. Run 200 images first, read the number the
     summarise step prints, then decide how to shard the other 3,900.

Filename conventions assumed (both are tolerated, and unparseable names are
still processed, just with blank metadata columns):

    hits/<cam>/<YYYYMMDD>/HHMMSS_p<preset>_blob<blob>.jpg
    frames/<cam>/<YYYYMMDD>/HHMMSS_p<preset>_blob<blob>_f<fill>.jpg

Times. The HHMMSS in the filename is the UTC key used by logs/<cam>/<date>.csv,
so it is carried through unchanged as the join key. Two derived columns are
added for reading convenience:

    sast        = utc + 2h00m00s   (true park local time, use this one)
    burnt_in    = utc + 1h51m45s   (what the burnt-in stamp should read, and
                                    therefore a cross-check on the frame)

burnt_in is left blank for satara, whose burnt-in clock is not usable.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# Detector grid, so MegaDetector's box can be read in the same units as the
# logged blob box. 384 x 216 at 4 px blocks.
GRID_W = 96
GRID_H = 54

SAST_OFFSET = timedelta(hours=2)
BURNT_IN_OFFSET = timedelta(hours=1, minutes=51, seconds=45)
NO_BURNT_IN = {"satara"}

# Matches watch.py: local = utc + tz, night is 18:00 to 06:00 local, tz is +2
# at all three cameras. Recomputed here rather than read from the log so that a
# frame with no log row still gets a mode.
TZ_HOURS = 2
NIGHT_FROM, NIGHT_TO = 18, 6

NAME_RE = re.compile(
    r"^(?P<hhmmss>\d{6})_p(?P<preset>\d+)_blob(?P<blob>\d+)"
    r"(?:_f(?P<fill>[0-9.]+))?\.jpe?g$",
    re.IGNORECASE,
)

DEFAULT_LABELS = os.path.join("tools", "ground_truth.txt")


# --------------------------------------------------------------------------
# ground truth
# --------------------------------------------------------------------------

def load_labels(path):
    """Return the set of '<cam>/<date>/<hhmmss>' keys confirmed to hold an
    animal. Missing file is not fatal: the harness still runs, it just cannot
    score."""
    keys = set()
    if not path or not os.path.exists(path):
        return keys
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            keys.add(line.replace("\\", "/"))
    return keys


def split_prediction(raw):
    """`<uuid>;<class>;<order>;<family>;<genus>;<species>;<common>` ->
    (class, common). Short or empty strings degrade to ("", raw)."""
    if not raw:
        return "", ""
    parts = raw.split(";")
    if len(parts) < 7:
        return "", raw
    return parts[1], parts[-1]


def frame_key(row):
    if not (row["cam"] and row["date"] and row["utc"]):
        return ""
    return f"{row['cam']}/{row['date']}/{row['utc'][11:].replace(':', '')}"


# --------------------------------------------------------------------------
# logs
# --------------------------------------------------------------------------

def load_logs(logs_root="logs"):
    """(cam, 'YYYY-MM-DD HH:MM:SS') -> log row dict.

    Parsed BY FIELD COUNT. See note 3 in the module docstring: three files
    contain rows wider than their own header and a header-driven parser
    silently misaligns them.
    """
    schemas = {}
    files = sorted(glob.glob(os.path.join(logs_root, "*", "*.csv")))
    for f in files:
        try:
            with open(f, newline="", encoding="utf-8") as fp:
                hdr = next(csv.reader(fp), [])
        except OSError:
            continue
        if hdr and hdr[0] == "utc":
            schemas.setdefault(len(hdr), hdr)

    out = {}
    mixed = 0
    for f in files:
        cam = os.path.basename(os.path.dirname(f))
        try:
            with open(f, newline="", encoding="utf-8") as fp:
                rd = csv.reader(fp)
                hdr = next(rd, [])
                for raw in rd:
                    if not raw:
                        continue
                    schema = schemas.get(len(raw))
                    if schema is None:
                        continue
                    if len(raw) != len(hdr):
                        mixed += 1
                    row = dict(zip(schema, raw))
                    out[(cam, row.get("utc", ""))] = row
        except OSError:
            continue
    if mixed:
        print(f"log parser: {mixed} rows were wider than their file header "
              f"and were realigned by field count")
    return out


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def parse_path(path):
    """Pull cam, date, utc, mode, preset, blob, fill out of an archive path."""
    parts = path.replace("\\", "/").split("/")
    out = {
        "path": path,
        "source": "",
        "cam": "",
        "date": "",
        "utc": "",
        "sast": "",
        "burnt_in": "",
        "mode": "",
        "preset": "",
        "logged_blob": "",
        "logged_fill": "",
    }
    if len(parts) >= 4:
        out["source"] = parts[-4]
        out["cam"] = parts[-3]
        out["date"] = parts[-2]

    m = NAME_RE.match(parts[-1])
    if not m:
        return out

    out["preset"] = m.group("preset")
    out["logged_blob"] = m.group("blob").lstrip("0") or "0"
    out["logged_fill"] = m.group("fill") or ""

    if re.fullmatch(r"\d{8}", out["date"]):
        try:
            ts = datetime.strptime(
                out["date"] + m.group("hhmmss"), "%Y%m%d%H%M%S"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            return out
        out["utc"] = ts.strftime("%Y-%m-%d %H:%M:%S")
        out["sast"] = (ts + SAST_OFFSET).strftime("%Y-%m-%d %H:%M:%S")
        if out["cam"] not in NO_BURNT_IN:
            out["burnt_in"] = (ts + BURNT_IN_OFFSET).strftime("%Y-%m-%d %H:%M:%S")
        local = (ts.hour + TZ_HOURS) % 24
        out["mode"] = "night" if (local >= NIGHT_FROM or local < NIGHT_TO) else "day"
    return out


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------

def cmd_list(args):
    cameras = [c.strip() for c in args.cameras.split(",") if c.strip()]
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    labels = load_labels(args.labels)

    found = []
    for root in roots:
        for cam in cameras:
            base = os.path.join(root, cam)
            if not os.path.isdir(base):
                print(f"skip (missing): {base}")
                continue
            for day in sorted(os.listdir(base)):
                if dates and day not in dates:
                    continue
                daydir = os.path.join(base, day)
                if not os.path.isdir(daydir):
                    continue
                for name in sorted(os.listdir(daydir)):
                    if name.lower().endswith((".jpg", ".jpeg")):
                        found.append(os.path.join(daydir, name))

    found.sort()
    total = len(found)

    if args.only in ("animals", "empties"):
        if not labels:
            print(f"--only {args.only} requested but no labels were loaded "
                  f"from {args.labels}; scanning everything instead")
        else:
            want_animal = args.only == "animals"
            found = [p for p in found
                     if (frame_key(parse_path(p)) in labels) == want_animal]

    selected_before_slice = len(found)
    if args.offset:
        found = found[args.offset:]
    if args.limit:
        found = found[: args.limit]

    with open(args.out, "w", encoding="utf-8") as fp:
        for p in found:
            fp.write(os.path.abspath(p) + "\n")

    unparsed = sum(1 for p in found if not parse_path(p)["utc"])
    print(f"archive total:         {total}")
    print(f"after --only {args.only:8s}: {selected_before_slice}")
    print(f"selected:              {len(found)}")
    print(f"unparseable filenames: {unparsed}")
    print(f"labels loaded:         {len(labels)} animal frames")
    by = {}
    for p in found:
        r = parse_path(p)
        by[(r["cam"] or "?", r["mode"] or "?")] = \
            by.get((r["cam"] or "?", r["mode"] or "?"), 0) + 1
    for k, n in sorted(by.items()):
        print(f"  {k[0]} {k[1]}: {n}")


# --------------------------------------------------------------------------
# summarise
# --------------------------------------------------------------------------

FIELDS = [
    "path", "source", "cam", "date", "utc", "sast", "burnt_in", "mode",
    "label",
    "preset", "logged_blob", "logged_fill", "logged_hit",
    "logged_dist", "logged_nblobs", "logged_n",
    "prediction_common", "prediction_class",
    "prediction", "prediction_score", "prediction_source",
    "top1_common", "top1_class", "top1_score",
    "n_detections", "md_label", "md_conf", "md_animal_conf",
    "md_bw_blocks", "md_bh_blocks", "md_cx", "md_cy", "md_area_blocks",
    "failures", "model_version",
]

THRESHOLDS = (0.1, 0.2, 0.5)


def cmd_summarise(args):
    with open(args.predictions, encoding="utf-8") as fp:
        data = json.load(fp)
    preds = data.get("predictions", [])

    labels = load_labels(args.labels)
    logs = load_logs(args.logs)

    rows = []
    for p in preds:
        row = parse_path(p.get("filepath", ""))
        key = frame_key(row)
        if not labels:
            row["label"] = ""
        else:
            row["label"] = "animal" if key in labels else "empty"

        lg = logs.get((row["cam"], row["utc"]))
        row["logged_hit"] = lg.get("hit", "") if lg else ""
        row["logged_dist"] = lg.get("dist", "") if lg else ""
        row["logged_nblobs"] = lg.get("nblobs", "") if lg else ""
        row["logged_n"] = lg.get("n", "") if lg else ""

        row["prediction"] = p.get("prediction", "")
        row["prediction_class"], row["prediction_common"] = \
            split_prediction(row["prediction"])
        row["prediction_score"] = p.get("prediction_score", "")
        row["prediction_source"] = p.get("prediction_source", "")
        row["failures"] = ";".join(p.get("failures", []))
        row["model_version"] = p.get("model_version", "")

        cls = p.get("classifications") or {}
        classes = cls.get("classes") or []
        scores = cls.get("scores") or []
        raw_top1 = classes[0] if classes else ""
        row["top1_class"], row["top1_common"] = split_prediction(raw_top1)
        row["top1_score"] = scores[0] if scores else ""

        dets = p.get("detections") or []
        row["n_detections"] = len(dets)

        # Maximum confidence over ALL detections labelled `animal`, not the
        # top detection only. See note 4 in the module docstring.
        animal_confs = []
        for d in dets:
            if d.get("label") == "animal":
                try:
                    animal_confs.append(float(d.get("conf", 0)))
                except (TypeError, ValueError):
                    pass
        row["md_animal_conf"] = max(animal_confs) if animal_confs else 0.0

        if dets:
            d = dets[0]
            row["md_label"] = d.get("label", "")
            row["md_conf"] = d.get("conf", "")
            x, y, w, h = (d.get("bbox") or [0, 0, 0, 0])
            bw = round(w * GRID_W, 1)
            bh = round(h * GRID_H, 1)
            row["md_bw_blocks"] = bw
            row["md_bh_blocks"] = bh
            row["md_cx"] = round(x + w / 2, 3)
            row["md_cy"] = round(y + h / 2, 3)
            row["md_area_blocks"] = round(bw * bh, 1)
        else:
            for k in ("md_label", "md_conf", "md_bw_blocks", "md_bh_blocks",
                      "md_cx", "md_cy", "md_area_blocks"):
                row[k] = ""
        rows.append(row)

    rows.sort(key=lambda r: (r["cam"], r["utc"], r["path"]))

    with open(args.out, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    print(f"\nrows: {n}  ->  {args.out}")
    if args.wall_seconds and n:
        print(f"\nWALL CLOCK: {args.wall_seconds:.0f}s for {n} images = "
              f"{args.wall_seconds / n:.2f} s/image")
        print(f"  4,109 archived frames would take "
              f"{args.wall_seconds / n * 4109 / 60:.0f} minutes at this rate.")
        print(f"  A day of Kruger daylight hits (about 137) would take "
              f"{args.wall_seconds / n * 137 / 60:.1f} minutes.")

    scored = [r for r in rows if r["label"] in ("animal", "empty")]
    if not scored:
        print("\nNo ground-truth labels loaded, so no scoring. "
              f"Expected them at {args.labels}.")
        _tallies(rows)
        return

    _score(scored, args)
    _tallies(rows)


def _rate(hits, total):
    return f"{hits:4d}/{total:<4d} {hits / total * 100:5.1f}%" if total else "   -/-        "


def _score(rows, args):
    """Recall and false positives in the same table, which is the whole point."""
    groups = sorted({(r["cam"], r["mode"]) for r in rows})

    print("\n" + "=" * 78)
    print("STAGE 2 ALONE: does SpeciesNet see an animal?")
    print("An 'animal' detection at or above the confidence threshold.")
    print("=" * 78)
    for t in THRESHOLDS:
        print(f"\n-- MegaDetector `animal` at conf >= {t} --")
        print(f"  {'cam / mode':18}{'recall on animal frames':>26}"
              f"{'fires on empty frames':>26}")
        for g in groups:
            pos = [r for r in rows if (r["cam"], r["mode"]) == g and r["label"] == "animal"]
            neg = [r for r in rows if (r["cam"], r["mode"]) == g and r["label"] == "empty"]
            rp = sum(1 for r in pos if float(r["md_animal_conf"] or 0) >= t)
            rn = sum(1 for r in neg if float(r["md_animal_conf"] or 0) >= t)
            print(f"  {g[0] + ' ' + g[1]:18}{_rate(rp, len(pos)):>26}{_rate(rn, len(neg)):>26}")

    print("\n" + "=" * 78)
    print("STAGE 1 AND STAGE 2 TOGETHER, at conf >= 0.2")
    print("Rows where the log row was found, so `logged_hit` is known.")
    print("=" * 78)
    t = 0.2
    print(f"  {'cam / mode':18}{'label':8}{'s1 only':>9}{'s2 only':>9}"
          f"{'both':>7}{'neither':>9}")
    for g in groups:
        for lab in ("animal", "empty"):
            sub = [r for r in rows
                   if (r["cam"], r["mode"]) == g and r["label"] == lab
                   and r["logged_hit"] in ("0", "1")]
            if not sub:
                continue
            def cell(s1, s2):
                return sum(1 for r in sub
                           if (r["logged_hit"] == "1") == s1
                           and (float(r["md_animal_conf"] or 0) >= t) == s2)
            print(f"  {g[0] + ' ' + g[1]:18}{lab:8}"
                  f"{cell(True, False):9}{cell(False, True):9}"
                  f"{cell(True, True):7}{cell(False, False):9}")

    print("\n  READ IT LIKE THIS. 's2 only' on an animal row is an animal the")
    print("  geometric detector missed and SpeciesNet would have found: that is")
    print("  the recall case for wiring stage 2 in. 'both' on an EMPTY row is a")
    print("  false positive stage 2 does NOT filter, which is the number that")
    print("  decides whether opening the daylight gates is affordable.")

    print("\n" + "=" * 78)
    print("WHAT IT CALLS THE ANIMALS (label=animal, conf >= 0.2)")
    print("=" * 78)
    tal = {}
    for r in rows:
        if r["label"] == "animal" and float(r["md_animal_conf"] or 0) >= 0.2:
            k = (r["cam"], r["prediction_common"] or "(blank)")
            tal[k] = tal.get(k, 0) + 1
    for k, v in sorted(tal.items(), key=lambda kv: (kv[0][0], -kv[1]))[:60]:
        print(f"  {k[0]:10}{v:5d}  {k[1]}")

    if args.score_out:
        with open(args.score_out, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(["cam", "mode", "label", "n_frames", "threshold",
                        "md_animal_hits", "share", "stage1_hits"])
            for g in groups:
                for lab in ("animal", "empty"):
                    sub = [r for r in rows
                           if (r["cam"], r["mode"]) == g and r["label"] == lab]
                    if not sub:
                        continue
                    s1 = sum(1 for r in sub if r["logged_hit"] == "1")
                    for t in THRESHOLDS:
                        k = sum(1 for r in sub
                                if float(r["md_animal_conf"] or 0) >= t)
                        w.writerow([g[0], g[1], lab, len(sub), t, k,
                                    round(k / len(sub), 4), s1])
        print(f"\nscores -> {args.score_out}")


def _tallies(rows):
    def tally(key):
        out = {}
        for r in rows:
            out[r.get(key) or "(blank)"] = out.get(r.get(key) or "(blank)", 0) + 1
        return sorted(out.items(), key=lambda kv: -kv[1])

    print("\n-- taxonomic class, all rows --")
    for k, v in tally("prediction_class")[:15]:
        print(f"  {v:5d}  {k}")

    print("\n-- final prediction, all rows --")
    for k, v in tally("prediction_common")[:30]:
        print(f"  {v:5d}  {k}")

    print("\n-- failures --")
    for k, v in tally("failures")[:10]:
        print(f"  {v:5d}  {k}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list")
    p1.add_argument("--cameras", default="nossob,talamati,satara")
    p1.add_argument("--roots", default="hits,frames")
    p1.add_argument("--dates", default="")
    p1.add_argument("--limit", type=int, default=0)
    p1.add_argument("--offset", type=int, default=0)
    p1.add_argument("--only", default="all",
                    choices=["all", "animals", "empties"])
    p1.add_argument("--labels", default=DEFAULT_LABELS)
    p1.add_argument("--out", default="filepaths.txt")
    p1.set_defaults(func=cmd_list)

    p2 = sub.add_parser("summarise")
    p2.add_argument("--predictions", default="predictions.json")
    p2.add_argument("--out", default="identify_test.csv")
    p2.add_argument("--score-out", default="identify_score.csv")
    p2.add_argument("--labels", default=DEFAULT_LABELS)
    p2.add_argument("--logs", default="logs")
    p2.add_argument("--wall-seconds", type=float, default=0)
    p2.set_defaults(func=cmd_summarise)

    args = ap.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
