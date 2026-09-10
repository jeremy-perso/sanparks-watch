#!/usr/bin/env python3
"""
draw_boxes.py

Draws the logged blob box, and MegaDetector's box where one is known, onto the
archived JPEGs, so "is the box on the animal" can be answered by looking rather
than by arithmetic. Read-only on the repo: writes only into --out.

    python tools/draw_boxes.py --only unreviewed --out annotated

RED   the logged blob box from logs/<cam>/<date>.csv: cx, cy, bw, bh.
       This is the one the review question is about.
GREEN MegaDetector's highest-confidence animal box, from --identify-csv.
       Shown for contrast only; it is not what stage 1 measured.

A caption strip is burnt along the bottom with the numbers that matter, so a
loose annotated JPEG still says what it is.

SELECTION IS BY EYE LABEL, WHICH IS WHY --only animals GOES BLIND.
ground_truth.txt and reviewed.txt are hand-maintained and frozen at the instant
of the last review pass. A frame archived after that instant is in neither, so
it is `unreviewed`, and --only animals, empties and reviewed all skip it. The
set that carries new frames is --only unreviewed, which empties itself again as
soon as the new keys are appended to the label files. --only all ignores the
label files entirely.

THE GREEN BOX COMES FROM species/, NOT FROM tools/identify_test.csv.
--identify-csv takes a comma-separated list of paths and globs, so the daily
production output of tools/identify.py can be read directly. The two schemas are
the same in the columns used here. On a key present in more than one file the
highest md_animal_conf wins.

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

THE GREEN BOX IS MATCHED TO THE COPY BEING DRAWN. Changed 10 Sep 2026. The
same instant can exist twice, as the full-resolution hits/ JPEG and the 900 px
frames/ copy, and SpeciesNet scores each separately. MegaDetector moves its box
or its confidence between the two on most such pairs (19 measured 10 Sep), so a
key is (cam, utc, source). A frame is drawn with the MD box of its own copy;
only when that copy was never scored does it fall back to the other copy's
best box, and the caption then says "MD from <source> copy".

LABELS SIT OUTSIDE THEIR BOXES. Changed 10 Sep 2026. "blob" goes above the red
box and "MD" below the green one, flipping side only when the frame edge
forces it. Drawn inside a 2 to 4 block box they covered exactly what was being
judged, twice on 10 Sep.

--md-min IS A TRIAGE CONTROL AND NOT A SAMPLING ONE. It keeps only frames whose
MegaDetector confidence clears a floor, which is useful for cutting a 400-frame
day down to something reviewable. Any set drawn with it is biased toward stage 2
agreement and must not be used to price a stage 1 gate.
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


def expand(spec):
    """Comma-separated paths and globs -> list of existing files, deduped."""
    out = []
    for pat in [p.strip() for p in (spec or "").split(",") if p.strip()]:
        hits = sorted(glob.glob(pat)) if any(c in pat for c in "*?[") else [pat]
        for h in hits:
            if os.path.isfile(h) and h not in out:
                out.append(h)
    return out


def load_md(spec):
    """(cam, utc, source) -> (cx, cy, bw_blocks, bh_blocks, conf, label, keep,
    keep_conf, source), plus (cam, utc, "") -> the best box over every source.

    Reads any number of identify outputs: the daily species/<cam>/<date>.csv
    written by tools/identify.py, and the older hand-committed
    tools/identify_test.csv. `source` is the archive root the scored JPEG came
    from (hits or frames); a file without that column files under "" only.
    Highest md_animal_conf wins on a repeated key.
    """
    out, files = {}, expand(spec)

    def put(key, val):
        prev = out.get(key)
        if prev is None or val[4] > prev[4]:
            out[key] = val

    # A copy that was scored keeps its own verdict even when it has no box
    # worth drawing (conf under 0.05 or no coordinates): the frame is then drawn
    # with no green box rather than borrowing the other copy's, and --md-min
    # judges it on its own confidence. Only the "" fallback key requires a box.
    for f in files:
        for r in csv.DictReader(open(f, newline="", encoding="utf-8")):
            try:
                conf = float(r.get("md_animal_conf") or 0)
                src = (r.get("source") or "").strip()
                tail = (conf, r.get("prediction_common", ""),
                        r.get("keep", ""), r.get("keep_conf", ""), src)
                drawable = conf >= 0.05 and bool(r.get("md_cx"))
                geo = ((float(r["md_cx"]), float(r["md_cy"]),
                        float(r["md_bw_blocks"]), float(r["md_bh_blocks"]))
                       if drawable else (None, None, None, None))
                val = geo + tail
                if src:
                    put((r["cam"], r["utc"], src), val)
                if drawable:
                    put((r["cam"], r["utc"], ""), val)
            except (ValueError, KeyError):
                continue
    n = len({k[:2] for k, v in out.items() if v[0] is not None})
    print(f"MD boxes: {n} keys with a drawable box from {len(files)} identify file(s)")
    if spec and not files:
        print("MD boxes: none of the --identify-csv paths matched a file, "
              "the green box will be absent")
    return out


def md_for(md, cam, utc, root):
    """The MD box scored on this very copy, else the best box of any copy."""
    own = md.get((cam, utc, root))
    if own is not None:
        return own
    return md.get((cam, utc, ""))


def label_xy(d, text, fnt, x0, y0, x1, y1, W, H, above):
    """Top-left for a label hugging the box from outside, clamped to the frame."""
    tb = d.textbbox((0, 0), text, font=fnt)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    gap = 3
    ya, yb = y0 - th - gap - tb[1], y1 + gap - tb[1]
    fits_a, fits_b = ya + tb[1] >= 0, yb + tb[1] + th <= H
    if above:
        y = ya if fits_a else (yb if fits_b else y0 + gap - tb[1])
    else:
        y = yb if fits_b else (ya if fits_a else y1 - th - gap - tb[1])
    x = min(max(2, x0), max(2, W - tw - 2))
    return x, y


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


def annotate(src, dst, row, md, label, root=""):
    im = Image.open(src).convert("RGB")
    W, H = im.size
    strip = max(34, H // 14)
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
        f1 = font(max(12, W // 60))
        d.text(label_xy(d, "blob", f1, x0, y0, x1, y1, W, H, above=True),
               "blob", fill=RED, font=f1)
        bits.append(f"blob {num('blob', 0):.0f} at {bw:.0f}x{bh:.0f} blocks"
                    f"  fill {num('fill', 0):.2f}  dom {num('dom', 0):.2f}"
                    f"  nblobs {num('nblobs', 0):.0f}  dist {num('dist', 0):.1f}"
                    f"  n {num('n', 0):.0f}"
                    f"  stage1 {'HIT' if num('hit', 0) == 1 else 'miss'}")
    else:
        bits.append("no CSV row for this frame, nothing to draw")

    if md and md[0] is None:
        bits.append(f"MD {md[4]:.2f} on this copy, no box to draw")
    elif md:
        mcx, mcy, mbw, mbh, conf, common, keep, keep_conf, msrc = md
        x0, y0, x1, y1 = box(mcx, mcy, mbw, mbh, W, H)
        d.rectangle([x0, y0, x1, y1], outline=GREEN, width=lw)
        f1 = font(max(12, W // 60))
        d.text(label_xy(d, "MD", f1, x0, y0, x1, y1, W, H, above=False),
               "MD", fill=GREEN, font=f1)
        tail = f"  stage2 {'KEEP' if keep == '1' else 'drop'} at {keep_conf}" if keep else ""
        other = f" from {msrc} copy" if msrc and msrc != root else ""
        bits.append(f"MD{other} {conf:.2f} {mbw:.1f}x{mbh:.1f} blocks {common}{tail}")
    else:
        bits.append("no MD box for this frame")

    line = strip // 2
    d.text((6, H + 2), label, fill=WHITE, font=font(max(11, line - 4)))
    tail = "  |  ".join(bits)
    for size in range(max(10, line - 5), 7, -1):
        f2 = font(size)
        if d.textlength(tail, font=f2) <= W - 12:
            break
    d.text((6, H + 2 + line), tail, fill=(190, 190, 190), font=f2)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.save(dst, quality=88)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", default="hits,frames")
    ap.add_argument("--cameras", default="nossob,talamati,satara")
    ap.add_argument("--dates", default="", help="comma-separated YYYYMMDD, exact match")
    ap.add_argument("--since", default="", help="YYYYMMDD, inclusive lower bound on the day")
    ap.add_argument("--until", default="", help="YYYYMMDD, inclusive upper bound on the day")
    ap.add_argument("--only", default="unreviewed",
                    choices=["all", "animals", "empties", "reviewed", "unreviewed"])
    ap.add_argument("--labels", default=os.path.join("tools", "ground_truth.txt"))
    ap.add_argument("--reviewed", default=os.path.join("tools", "reviewed.txt"))
    ap.add_argument("--identify-csv", default=os.path.join("species", "*", "*.csv"))
    ap.add_argument("--md-min", type=float, default=0.0,
                    help="triage only: keep frames whose MD confidence clears this. "
                         "Biases the set toward stage 2, do not price a gate with it.")
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--out", default="annotated")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    a = ap.parse_args()

    labels, reviewed = load_keys(a.labels), load_keys(a.reviewed)
    print(f"eye labels: {len(labels)} animal, {len(reviewed)} reviewed")
    logs, md = load_logs(a.logs), load_md(a.identify_csv)

    days = [d.strip() for d in a.dates.split(",") if d.strip()]
    found, dropped_md = [], 0
    for root in [r.strip() for r in a.roots.split(",") if r.strip()]:
        for cam in [c.strip() for c in a.cameras.split(",") if c.strip()]:
            base = os.path.join(root, cam)
            if not os.path.isdir(base):
                continue
            for day in sorted(os.listdir(base)):
                if days and day not in days:
                    continue
                if a.since and day < a.since:
                    continue
                if a.until and day > a.until:
                    continue
                dd = os.path.join(base, day)
                if not os.path.isdir(dd):
                    continue
                for nm in sorted(os.listdir(dd)):
                    m = NAME_RE.match(nm)
                    if not m:
                        continue
                    hh = m.group("hh")
                    key = f"{cam}/{day}/{hh}"
                    lab = ("animal" if key in labels else
                           "empty" if key in reviewed else "unreviewed")
                    if a.only == "animals" and lab != "animal":
                        continue
                    if a.only == "empties" and lab != "empty":
                        continue
                    if a.only == "reviewed" and lab == "unreviewed":
                        continue
                    if a.only == "unreviewed" and lab != "unreviewed":
                        continue
                    utc = f"{day[:4]}-{day[4:6]}-{day[6:]} {hh[:2]}:{hh[2:4]}:{hh[4:]}"
                    if a.md_min > 0:
                        mm = md_for(md, cam, utc, root)
                        if mm is None or mm[4] < a.md_min:
                            dropped_md += 1
                            continue
                    found.append((os.path.join(dd, nm), root, cam, day, m, lab, utc))

    total = len(found)
    if a.offset:
        found = found[a.offset:]
    if a.limit:
        found = found[:a.limit]
    if a.md_min > 0:
        print(f"--md-min {a.md_min}: {dropped_md} frames dropped below the floor. "
              f"This set is biased toward stage 2 and cannot price a stage 1 gate.")
    print(f"matched {total}, drawing {len(found)}")
    if total == 0:
        print("nothing matched. If --only is animals, empties or reviewed, remember "
              "the label files are frozen at the last review pass and every newer "
              "frame is unreviewed. Try --only unreviewed.")

    drawn = norow = nomd = 0
    for src, root, cam, day, m, lab, utc in found:
        row = logs.get((cam, utc))
        if row is None:
            norow += 1
        mdbox = md_for(md, cam, utc, root)
        if mdbox is None:
            nomd += 1
        label = (f"{cam} {utc} UTC  p{m.group('preset')}  {root}/  "
                 f"eye label: {lab}")
        dst = os.path.join(a.out, cam, day, f"{root}_{m.group(0)}")
        annotate(src, dst, row, mdbox, label, root)
        drawn += 1
    print(f"drew {drawn} into {a.out}/   ({norow} had no CSV row, {nomd} had no MD box)")


if __name__ == "__main__":
    sys.exit(main())
