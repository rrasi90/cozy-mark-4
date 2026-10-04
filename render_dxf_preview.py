"""Render COZY3V_digitized.json to labelled preview images (reading aid only).

Needs Pillow, so it runs with the system Python, not the OpenVSP one:

    python render_dxf_preview.py

Outputs:
    COZY3V_preview.png          whole sheet, colour-coded by view
    COZY3V_preview_<view>.png   one crop per view, each polyline labelled
                                "<view letter><entity index>"

Labels refer to the "index" field of COZY3V_digitized.json, i.e. the position
of the entity inside the DXF ENTITIES section. The preview is not a
measurement source; only the JSON is.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "COZY3V_digitized.json"

VIEW_COLOR = {
    "top": (20, 110, 220),
    "front": (220, 60, 30),
    "side": (20, 150, 70),
}
VIEW_LETTER = {"top": "T", "front": "F", "side": "S"}
VIEW_MARGIN = {  # drawing units added around each view crop
    "top": 0.45, "front": 0.60, "side": 0.45,
}


def load():
    doc = json.loads(SOURCE.read_text(encoding="utf-8"))
    polylines = [e for e in doc["entities"] if e["type"] in ("POLYLINE", "LINE")]
    texts = [e for e in doc["entities"] if e["type"] in ("TEXT", "MTEXT")]
    arrows = [e for e in doc["entities"] if e["type"] == "SHAPE"]
    return doc, polylines, texts, arrows


def extents(items, key="points_units"):
    boxes = []
    for item in items:
        if key in item:
            boxes.append(item["bbox_units"])
        else:
            x, y = item["position_units"]
            boxes.append([x, y, x, y])
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def font(size):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(polylines, texts, arrows, box, pixels_wide, path, labels=True):
    x0, y0, x1, y1 = box
    width_units, height_units = x1 - x0, y1 - y0
    scale = pixels_wide / width_units
    height_px = max(1, int(round(height_units * scale)))
    image = Image.new("RGB", (pixels_wide, height_px), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    def to_px(x, y):
        return ((x - x0) * scale, (y1 - y) * scale)

    for item in arrows:
        px, py = to_px(*item["position_units"])
        r = max(2, item.get("height_units", 0.16) * scale * 0.5)
        draw.ellipse([px - r, py - r, px + r, py + r], outline=(90, 90, 90))

    for item in texts:
        px, py = to_px(*item["position_units"])
        size = max(9, int((item.get("height_units") or 0.11) * scale))
        draw.text((px, py), item["text"], fill=(60, 60, 60), font=font(size),
                  anchor="lm")

    for item in polylines:
        color = VIEW_COLOR.get(item["view"], (0, 0, 0))
        pts = [to_px(x, y) for x, y in item["points_units"]]
        if len(pts) == 1:
            draw.ellipse([pts[0][0] - 1, pts[0][1] - 1, pts[0][0] + 1, pts[0][1] + 1],
                         fill=color)
        else:
            draw.line(pts, fill=color, width=2)
        if labels and item["n_points"] > 2:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            draw.text((cx, cy), f"{VIEW_LETTER.get(item['view'], '?')}{item['index']}",
                      fill=(200, 0, 0), font=font(11), anchor="mm")

    image.save(path)
    print("wrote", path, image.size)


def main():
    if not SOURCE.is_file():
        raise SystemExit(f"Missing {SOURCE}; run digitize_dxf.py first")
    doc, polylines, texts, arrows = load()
    scale = doc["scale"]["ft_per_unit"]

    all_box = extents(polylines + texts + arrows)
    render(polylines, texts, arrows, all_box, 1700, HERE / "COZY3V_preview.png",
           labels=False)

    for view in ("top", "front", "side"):
        subset = [p for p in polylines if p["view"] == view]
        if not subset:
            print("no entities for view", view)
            continue
        box = extents(subset)
        margin = VIEW_MARGIN[view]
        box = [box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin]

        def inside(item):
            x, y = item["position_units"]
            return box[0] <= x <= box[2] and box[1] <= y <= box[3]

        render(subset, [t for t in texts if inside(t)],
               [a for a in arrows if inside(a)], box, 1500,
               HERE / f"COZY3V_preview_{view}.png", labels=True)

    print("scale_ft_per_unit", scale)
    print("counts", doc["view_classification"]["counts"])


if __name__ == "__main__":
    main()
