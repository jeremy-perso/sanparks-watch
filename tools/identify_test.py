#!/usr/bin/env python3
"""
identify_test.py

Evaluation harness only. Reads the archived JPEGs, hands them to SpeciesNet,
and joins the result back to the metadata already encoded in the filenames.

Writes nothing into the repo. Touches no detector code.

Two modes:

    python tools/identify_test.py list      --out filepaths.txt
    python tools/identify_test.py summarise --predictions predictions.json \
                                            --out identify_test.csv

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

NAME_RE = re.compile(
    r"^(?P<hhmmss>\d{6})_p(?P<preset>\d+)_blob(?P<blob>\d+)"
    r"(?:_f(?P<fill>[0-9.]+))?\.jpe?g$",
    re.IGNORECASE,
)


def parse_path(path):
    """Pull cam, date, utc, preset, blob, fill out of an archive path."""
    parts = path.replace("\\", "/").split("/")
    out = {
        "path": path,
        "source": "",
        "cam": "",
        "date": "",
        "utc": "",
        "sast": "",
        "burnt_in": "",
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
    return out


def cmd_list(args):
    cameras = [c.strip() for c in args.cameras.split(",") if c.strip()]
    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    dates = [d.strip() for d in args.dates.split(",") if d.strip()]

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
    if args.offset:
        found = found[args.offset:]
    if args.limit:
        found = found[: args.limit]

    with open(args.out, "w", encoding="utf-8") as fp:
        for p in found:
            fp.write(os.path.abspath(p) + "\n")

    unparsed = sum(1 for p in found if not parse_path(p)["utc"])
    print(f"archive total: {total}")
    print(f"selected:      {len(found)}")
    print(f"unparseable filenames: {unparsed}")
    by_cam = {}
    for p in found:
        by_cam[parse_path(p)["cam"] or "?"] = by_cam.get(parse_path(p)["cam"] or "?", 0) + 1
    for cam, n in sorted(by_cam.items()):
        print(f"  {cam}: {n}")


FIELDS = [
    "path", "source", "cam", "date", "utc", "sast", "burnt_in",
    "preset", "logged_blob", "logged_fill",
    "prediction", "prediction_score", "prediction_source",
    "top1_class", "top1_score",
    "n_detections", "md_label", "md_conf",
    "md_bw_blocks", "md_bh_blocks", "md_cx", "md_cy", "md_area_blocks",
    "failures", "model_version",
]


def cmd_summarise(args):
    with open(args.predictions, encoding="utf-8") as fp:
        data = json.load(fp)
    preds = data.get("predictions", [])

    rows = []
    for p in preds:
        row = parse_path(p.get("filepath", ""))
        row["prediction"] = p.get("prediction", "")
        row["prediction_score"] = p.get("prediction_score", "")
        row["prediction_source"] = p.get("prediction_source", "")
        row["failures"] = ";".join(p.get("failures", []))
        row["model_version"] = p.get("model_version", "")

        cls = p.get("classifications") or {}
        classes = cls.get("classes") or []
        scores = cls.get("scores") or []
        row["top1_class"] = classes[0] if classes else ""
        row["top1_score"] = scores[0] if scores else ""

        dets = p.get("detections") or []
        # Detections above 0.01 only, already sorted by confidence.
        row["n_detections"] = len(dets)
        if dets:
            d = dets[0]
            row["md_label"] = d.get("label", "")
            row["md_conf"] = d.get("conf", "")
            box = d.get("bbox") or [0, 0, 0, 0]
            x, y, w, h = box
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

    # Summary to the Actions log. This is the whole point of the run.
    n = len(rows)
    print(f"\nrows: {n}  ->  {args.out}")
    if args.wall_seconds and n:
        print(f"wall clock: {args.wall_seconds}s   "
              f"{args.wall_seconds / n:.2f} s/image")

    def tally(key, rowset):
        out = {}
        for r in rowset:
            out[r.get(key) or "(blank)"] = out.get(r.get(key) or "(blank)", 0) + 1
        return sorted(out.items(), key=lambda kv: -kv[1])

    print("\n-- final prediction, all rows --")
    for k, v in tally("prediction", rows)[:30]:
        print(f"  {v:5d}  {k}")

    print("\n-- any animal detection at conf >= 0.2, by camera --")
    for cam in sorted({r["cam"] for r in rows}):
        sub = [r for r in rows if r["cam"] == cam]
        pos = [r for r in sub
               if r["md_label"] == "animal"
               and r["md_conf"] not in ("", None)
               and float(r["md_conf"]) >= 0.2]
        print(f"  {cam}: {len(pos)} of {len(sub)}")

    print("\n-- failures --")
    for k, v in tally("failures", rows)[:10]:
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
    p1.add_argument("--out", default="filepaths.txt")
    p1.set_defaults(func=cmd_list)

    p2 = sub.add_parser("summarise")
    p2.add_argument("--predictions", default="predictions.json")
    p2.add_argument("--out", default="identify_test.csv")
    p2.add_argument("--wall-seconds", type=float, default=0)
    p2.set_defaults(func=cmd_summarise)

    args = ap.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
