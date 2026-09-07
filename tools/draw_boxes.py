#!/usr/bin/env python3
"""
draw_boxes.py

Draws the logged blob box, and MegaDetector's box where one is known, onto the
archived JPEGs, so "is the box on the animal" can be answered by looking rather
than by arithmetic. Read-only on the repo: writes only into --out.

    python tools/draw_boxes.py --only animals --out annotated

RED   the logged blob box from logs/<cam>/<date>.csv: cx, cy, bw, bh.
       This is the one the review question is about.
GREEN MegaDetector's highest-confidence animal box, if --identify-csv is given.
       Shown for contrast only; it is not what stage 1 measured.

A caption strip is burnt along the bottom with the numbers that matter, so a
loose annotated JPEG still says what it is.

THE GEOMETRY, stated once. watch.py resizes every frame to 384 x 216 before
blocking, so the grid is always 96 x 54 whatever the source resolution. On the
900 x 506 archived JPEG one block is 9.375 px. The box is

    x from cx*W - bw*(W/96)/2  to  cx*W + bw*(W/96)/2
    y from cy*H - bh*(H/54)/2  to  cy*H + bh*(H/54)/2

computed against the actual pixel size of the file being drawn on, so it is
correct for a 900 x 506 archive frame and for a 1920 x 1080 or 1280 x 720 raw
frame alike.

The log parser goes BY FIELD COUNT, not by header. Three files written before
the 4 September schema rotation carry rows wider than their own header
(logs/nossob/20260831.csv, logs/nossob/20260901.csv, logs/talamati/20260901.csv)
and a header-driven parser silently puts `bytes` into `hit` on 2,686 of them.
"""

import argparse, csv, glob, os, re, sys
from PIL import Image, ImageDraw, ImageFont

GRID_W, GRID_H = 96, 54
NAME_RE = re.compile(r"^(?P<hh>\d{6})_p(?P<preset>\d+)_blob(?P<blob>\d+)"
                     r"(?:_f(?P<fill>[0-9.]+))?\.jpe?g$", re.I)
RED, GREEN, BLACK, WHITE = (232, 62, 62), (60, 200, 120), (0, 0, 0), (255, 255, 255)


def load_keys(path):
    keys = set()
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                keys.add(line.replace("\\", "/"))
    return keys


def load_logs(root="logs"):
    schemas, files = {}, sorted(glob.glob(os.path.join(root, "*", "*.csv")))
    for f in files:
        h = next(csv.reader(open(f, newline="", encoding="utf-8")), [])
        if h and h[0] == "utc":
            schemas.setdefault(len(h), h)
    out, mixed = {}, 0
    for f in files:
        cam = os.path.basename(os.path.dirname(f))
        rd = csv.reader(open(f, newline="", encoding="utf-8"))
        hdr = next(rd, [])
        for raw in rd:
            if not raw:
                continue
            s = schemas.get(len(raw))
            if s is None:
                continue
            if len(raw) != len(hdr):
                mixed += 1
            r = dict(zip(s, raw))
            out[(cam, r.get("utc", ""))] = r
    if mixed:
        print(f"log parser: {mixed} rows realigned by field count")
    return out


def load_md(path):
    """(cam, utc) -> (cx, cy, bw_blocks, bh_blocks, conf, label)."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
        try:
            if float(r.get("md_animal_conf") or 0) < 0.05 or not r.get("md_cx"):
                continue
            out[(r["cam"], r["utc"])] = (
                float(r["md_cx"]), float(r["md_cy"]),
                float(r["md_bw_blocks"]), float(r["md_bh_blocks"]),
                float(r["md_animal_conf"]), r.get("prediction_common", ""))
        except (ValueError, KeyError):
            continue
    return out


def box(cx, cy, bw, bh, W, H):
    bx, by = W / GRID_W, H / GRID_H
    return (cx * W - bw * bx / 2, cy * H - bh * by / 2,
            cx * W + bw * bx / 2, cy * H + bh * by / 2)


def font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def annotate(src, dst, row, md, label):
    im = Image.open(src).convert("RGB")
    W, H = im.size
    strip = max(26, H // 22)
    out = Image.new("RGB", (W, H + strip), BLACK)
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    lw = max(2, W // 450)
    bits = []

    def num(k, default=None):
        v = (row or {}).get(k, "")
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    cx, cy = num("cx"), num("cy")
    bw, bh = num("bw"), num("bh")
    if None not in (cx, cy, bw, bh) and bw > 0 and bh > 0:
        x0, y0, x1, y1 = box(cx, cy, bw, bh, W, H)
        d.rectangle([x0, y0, x1, y1], outline=RED, width=lw)
        d.text((max(2, x0 + 3), max(2, y0 + 3)), "blob", fill=RED, font=font(max(12, W // 60)))
        bits.append(f"blob {num('blob', 0):.0f} at {bw:.0f}x{bh:.0f} blocks"
                    f"  fill {num('fill', 0):.2f}  dom {num('dom', 0):.2f}"
                    f"  nblobs {num('nblobs', 0):.0f}  dist {num('dist', 0):.1f}"
                    f"  n {num('n', 0):.0f}"
                    f"  stage1 {'HIT' if num('hit', 0) == 1 else 'miss'}")
    else:
        bits.append("no CSV row for this frame, nothing to draw")

    if md:
        mcx, mcy, mbw, mbh, conf, common = md
        x0, y0, x1, y1 = box(mcx, mcy, mbw, mbh, W, H)
        d.rectangle([x0, y0, x1, y1], outline=GREEN, width=lw)
        d.text((max(2, x0 + 3), max(2, y1 - 20)), "MD", fill=GREEN, font=font(max(12, W // 60)))
        bits.append(f"MD {conf:.2f} {common}")

    f = font(max(11, strip // 2))
    d.text((6, H + 4), label, fill=WHITE, font=f)
    d.text((6, H + 4 + strip // 2), "  |  ".join(bits), fill=(190, 190, 190), font=font(max(10, strip // 2 - 2)))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.save(dst, quality=88)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", default="hits,frames")
    ap.add_argument("--cameras", default="nossob,talamati,satara")
    ap.add_argument("--dates", default="")
    ap.add_argument("--only", default="animals",
                    choices=["all", "animals", "empties", "reviewed"])
    ap.add_argument("--labels", default=os.path.join("tools", "ground_truth.txt"))
    ap.add_argument("--reviewed", default=os.path.join("tools", "reviewed.txt"))
    ap.add_argument("--identify-csv", default="")
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--out", default="annotated")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    a = ap.parse_args()

    labels, reviewed = load_keys(a.labels), load_keys(a.reviewed)
    logs, md = load_logs(a.logs), load_md(a.identify_csv)

    found = []
    for root in [r.strip() for r in a.roots.split(",") if r.strip()]:
        for cam in [c.strip() for c in a.cameras.split(",") if c.strip()]:
            base = os.path.join(root, cam)
            if not os.path.isdir(base):
                continue
            for day in sorted(os.listdir(base)):
                if a.dates and day not in [d.strip() for d in a.dates.split(",")]:
                    continue
                dd = os.path.join(base, day)
                if not os.path.isdir(dd):
                    continue
                for nm in sorted(os.listdir(dd)):
                    m = NAME_RE.match(nm)
                    if not m:
                        continue
                    key = f"{cam}/{day}/{m.group('hh')}"
                    lab = ("animal" if key in labels else
                           "empty" if key in reviewed else "unreviewed")
                    if a.only == "animals" and lab != "animal":
                        continue
                    if a.only == "empties" and lab != "empty":
                        continue
                    if a.only == "reviewed" and lab == "unreviewed":
                        continue
                    found.append((os.path.join(dd, nm), root, cam, day, m, lab))

    total = len(found)
    if a.offset:
        found = found[a.offset:]
    if a.limit:
        found = found[:a.limit]
    print(f"matched {total}, drawing {len(found)}")

    drawn = norow = 0
    for src, root, cam, day, m, lab in found:
        hh = m.group("hh")
        utc = f"{day[:4]}-{day[4:6]}-{day[6:]} {hh[:2]}:{hh[2:4]}:{hh[4:]}"
        row = logs.get((cam, utc))
        if row is None:
            norow += 1
        label = (f"{cam} {utc} UTC  p{m.group('preset')}  {root}/  "
                 f"eye label: {lab}")
        dst = os.path.join(a.out, cam, day, f"{root}_{m.group(0)}")
        annotate(src, dst, row, md.get((cam, utc)), label)
        drawn += 1
    print(f"drew {drawn} into {a.out}/   ({norow} had no CSV row)")


if __name__ == "__main__":
    sys.exit(main())
