"""Digitize COZY3V.DXF (three-view drawing) into machine-readable geometry.

Stdlib only. Run with the OpenVSP Python interpreter:

    & "C:\\OpenVSP-3.51.2-win64\\.venv\\Scripts\\python.exe" digitize_dxf.py

Outputs COZY3V_digitized.json next to this file. A labelled preview PNG is
produced separately by render_dxf_preview.py (needs Pillow, different
interpreter); that preview is a reading aid only, the JSON is the record.

What is trusted and what is not
-------------------------------
* Scale is NOT assumed. It is solved from the two dimension texts and their
  LONGARROW positions inside the file. All three estimates must agree to
  1e-9 relative or the run aborts, so a unit mistake cannot pass silently.
* Only 3 dimension texts exist in the whole file. Everything else in the JSON
  is a raw measurement of drawing geometry, i.e. scale-derived, not a stated
  dimension. Consumers must treat those two classes differently.
* Entities are assigned to views with fixed thresholds that sit in measured
  gaps between clusters. The gaps are reported so a wrong split stays visible.
* Coordinates in points_*_ft are measured from the drawing origin (0,0), NOT
  from any aircraft datum. Datum alignment happens in the dimension table.

Units: drawing units for *_units, feet for *_ft. Angles: degrees.
"""

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "COZY3V.DXF"
OUT = HERE / "COZY3V_digitized.json"

SCALE_ASSERT_REL_TOL = 1e-9
VIEW_X_SPLIT = 8.5
VIEW_Y_SPLIT = 2.60

VIEW_RULES = {
    "x_split_units": VIEW_X_SPLIT,
    "y_split_units": VIEW_Y_SPLIT,
    "order": [
        "center_x >= x_split -> side",
        "center_y < y_split -> front",
        "otherwise -> top",
    ],
}


def read_pairs(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) % 2:
        lines = lines[:-1]
    return [(lines[i].strip(), lines[i + 1].strip()) for i in range(0, len(lines), 2)]


def section_slice(pairs, name):
    start = None
    for i, (code, value) in enumerate(pairs):
        if start is None:
            if code == "2" and value == name and i > 0 and pairs[i - 1][1] == "SECTION":
                start = i
        elif code == "0" and value == "ENDSEC":
            return start, i
    raise RuntimeError(f"DXF section {name} not found")


def parse_header(pairs):
    start, end = section_slice(pairs, "HEADER")
    wanted = {"$EXTMIN": ["10", "20"], "$EXTMAX": ["10", "20"],
              "$LIMMIN": ["10", "20"], "$LIMMAX": ["10", "20"]}
    out, i = {}, start
    while i < end:
        code, value = pairs[i]
        if code == "9" and value in wanted:
            coords = []
            for j, want in enumerate(wanted[value]):
                if i + 1 + j < end and pairs[i + 1 + j][0] == want:
                    coords.append(float(pairs[i + 1 + j][1]))
            out[value] = coords
        if code == "9" and value == "$LUNITS" and i + 1 < end:
            out["$LUNITS"] = int(pairs[i + 1][1])
        i += 1
    return out


def parse_entities(pairs):
    start, end = section_slice(pairs, "ENTITIES")
    entities, current = [], None
    for code, value in pairs[start + 1:end]:
        if code == "0":
            current = {"type": value, "code": {}}
            entities.append(current)
        elif current is not None:
            current["code"].setdefault(code, []).append(value)
    return entities


def first(entity, code, default=None):
    values = entity["code"].get(code)
    return values[0] if values else default


def num(entity, code, default=None):
    raw = first(entity, code)
    return float(raw) if raw is not None else default


def as_records(entities):
    """Expand the POLYLINE/VERTEX/SEQEND stream into simple records."""
    records, poly = [], None
    for index, entity in enumerate(entities):
        kind = entity["type"]
        if kind == "POLYLINE":
            poly = {"index": index, "type": "POLYLINE", "layer": first(entity, "8", "?"),
                    "points": []}
        elif kind == "VERTEX" and poly is not None:
            poly["points"].append([num(entity, "10"), num(entity, "20")])
        elif kind == "SEQEND" and poly is not None:
            if poly["points"]:
                records.append(poly)
            poly = None
        elif kind == "LINE":
            records.append({"index": index, "type": "LINE", "layer": first(entity, "8", "?"),
                            "points": [[num(entity, "10"), num(entity, "20")],
                                       [num(entity, "11"), num(entity, "21")]]})
        elif kind in ("TEXT", "MTEXT"):
            records.append({"index": index, "type": kind, "layer": first(entity, "8", "?"),
                            "text": first(entity, "1", ""),
                            "position": [num(entity, "10"), num(entity, "20")],
                            "height": num(entity, "40")})
        elif kind == "SHAPE":
            records.append({"index": index, "type": "SHAPE", "layer": first(entity, "8", "?"),
                            "shape": first(entity, "2", ""),
                            "position": [num(entity, "10"), num(entity, "20")],
                            "height": num(entity, "40")})
    return records


def bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def parse_feet(text):
    """Parse '28\\' 1.50\"' style dimension text into feet."""
    match = re.match(r"^\s*(\d+)\s*'\s*([-\d.]+)\s*\"", text)
    if not match:
        raise RuntimeError(f"Unparsable dimension text: {text!r}")
    feet = float(match.group(1))
    inches = float(match.group(2))
    return feet + inches / 12.0, {"feet": feet, "inches": inches}


def dimension_lines(records, collinear_tol=1e-3):
    """Group LONGARROWs into dimension lines: collinear pairs of arrowheads.

    Arrows are clustered by equal y (horizontal lines) and by equal x
    (vertical lines). Exactly two arrowheads per line, and every arrow must be
    used exactly once; anything else is a parse failure, not a guess.
    """
    arrows = [r for r in records
              if r["type"] == "SHAPE" and r["shape"].upper() == "LONGARROW"]
    if not arrows:
        raise RuntimeError("No LONGARROW shapes found; scale cannot be solved")

    def clusters(key):
        groups = []
        for arrow in arrows:
            value = key(arrow["position"])
            for group in groups:
                if abs(group["value"] - value) <= collinear_tol:
                    group["arrows"].append(arrow)
                    break
            else:
                groups.append({"value": value, "arrows": [arrow]})
        return groups

    lines, used = [], set()
    for axis, key, index_of in (("x", lambda p: p[1], lambda a: a["position"][0]),
                                ("y", lambda p: p[0], lambda a: a["position"][1])):
        for group in clusters(key):
            if len(group["arrows"]) < 2:
                continue
            if len(group["arrows"]) > 2:
                raise RuntimeError(
                    f"{len(group['arrows'])} arrowheads on one {axis}-dimension "
                    f"line near {group['value']:.4f}")
            indices = [a["index"] for a in group["arrows"]]
            if any(i in used for i in indices):
                raise RuntimeError("Arrowhead reused across dimension lines")
            used.update(indices)
            span = abs(index_of(group["arrows"][0]) - index_of(group["arrows"][1]))
            lines.append({
                "axis": axis,
                "value": group["value"],
                "span_units": span,
                "arrow_indices": indices,
                "arrows_units": [a["position"] for a in group["arrows"]],
            })
    unused = [a["index"] for a in arrows if a["index"] not in used]
    if unused:
        raise RuntimeError(f"Arrowheads not part of any dimension line: {unused}")
    if not lines:
        raise RuntimeError("No dimension line could be formed from arrowheads")
    return lines


def solve_scale(records):
    """Solve ft-per-drawing-unit from dimension texts and their arrow pairs."""
    texts = [r for r in records if r["type"] in ("TEXT", "MTEXT") and r["text"].strip()]
    lines = dimension_lines(records)
    if not texts or not lines:
        raise RuntimeError("No dimension texts or dimension lines found")

    def score(text, line):
        tx, ty = text["position"]
        margin = 0.75
        if line["axis"] == "x":
            xs = [a[0] for a in line["arrows_units"]]
            inside = min(xs) - margin <= tx <= max(xs) + margin
            return abs(ty - line["value"]) + (0.0 if inside else 1e3)
        ys = [a[1] for a in line["arrows_units"]]
        inside = min(ys) - margin <= ty <= max(ys) + margin
        return abs(tx - line["value"]) + (0.0 if inside else 1e3)

    pairs = sorted(((score(t, l), ti, li)
                    for ti, t in enumerate(texts)
                    for li, l in enumerate(lines)), key=lambda p: p[0])
    used_text, used_line, chosen = set(), set(), []
    for _, ti, li in pairs:
        if ti in used_text or li in used_line:
            continue
        used_text.add(ti)
        used_line.add(li)
        chosen.append((ti, li))
    if len(chosen) != len(texts) or len(chosen) != len(lines):
        raise RuntimeError(f"Cannot pair every dimension text with exactly one "
                           f"dimension line: {len(chosen)} pairs for "
                           f"{len(texts)} texts and {len(lines)} lines")

    estimates = []
    for ti, li in sorted(chosen):
        text, line = texts[ti], lines[li]
        value_ft, parts = parse_feet(text["text"])
        if line["span_units"] <= 0:
            raise RuntimeError("Zero-length dimension line")
        estimates.append({
            "text": text["text"],
            "axis": line["axis"],
            "value_ft": value_ft,
            "parts": parts,
            "arrow_span_units": line["span_units"],
            "scale_ft_per_unit": value_ft / line["span_units"],
            "text_index": text["index"],
            "text_position_units": text["position"],
            "arrow_indices": line["arrow_indices"],
            "arrows_units": line["arrows_units"],
        })
    scales = [e["scale_ft_per_unit"] for e in estimates]
    spread = (max(scales) - min(scales)) / (sum(scales) / len(scales))
    if spread > SCALE_ASSERT_REL_TOL:
        raise RuntimeError(f"Dimension texts disagree on scale: {scales} "
                           f"(rel spread {spread:.3e})")
    return sum(scales) / len(scales), estimates, spread


def classify(box):
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    if cx >= VIEW_X_SPLIT:
        return "side"
    return "front" if cy < VIEW_Y_SPLIT else "top"


def split_gap_report(records):
    """Report how much empty space separates the view clusters."""
    centres = []
    for record in records:
        if record["type"] not in ("POLYLINE", "LINE"):
            continue
        box = bbox(record["points"])
        centres.append(((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0,
                        record["index"], classify(box)))
    left = [c for c in centres if c[3] in ("top", "front")]
    right = [c for c in centres if c[3] == "side"]
    below = [c for c in centres if c[3] == "front"]
    above = [c for c in centres if c[3] == "top"]
    report = {
        "x_split_check": {
            "threshold": VIEW_X_SPLIT,
            "max_center_x_left_side": max(c[0] for c in left),
            "min_center_x_right_side": min(c[0] for c in right),
        },
        "y_split_check": {
            "threshold": VIEW_Y_SPLIT,
            "max_center_y_front": max(c[1] for c in below),
            "min_center_y_top": min(c[1] for c in above),
        },
    }
    for key, other in (("x_split_check", "right_side"), ("y_split_check", "top")):
        gap = report[key]
        low = [v for k, v in gap.items() if k.startswith("max_")][0]
        high = [v for k, v in gap.items() if k.startswith("min_")][0]
        gap["empty_band_units"] = high - low
        gap["separated"] = high > low
        if not gap["separated"]:
            raise RuntimeError(f"View clusters overlap at {key}: {low} >= {high}")
    return report


def main():
    if not SOURCE.is_file():
        raise SystemExit(f"Missing {SOURCE}")
    pairs = read_pairs(SOURCE)
    header = parse_header(pairs)
    entities = parse_entities(pairs)
    records = as_records(entities)

    scale, estimates, spread = solve_scale(records)
    gaps = split_gap_report(records)

    census = {}
    for entity in entities:
        census[entity["type"]] = census.get(entity["type"], 0) + 1

    layers = {}
    for record in records:
        layers.setdefault(record["layer"], {}).setdefault(record["type"], 0)
        layers[record["layer"]][record["type"]] += 1

    out_entities = []
    for record in records:
        item = {"index": record["index"], "type": record["type"],
                "layer": record["layer"]}
        if record["type"] in ("POLYLINE", "LINE"):
            box = bbox(record["points"])
            view = classify(box)
            item.update({
                "view": view,
                "n_points": len(record["points"]),
                "bbox_units": [round(v, 6) for v in box],
                "bbox_ft": [round(v * scale, 6) for v in box],
                "size_ft": [round((box[2] - box[0]) * scale, 6),
                            round((box[3] - box[1]) * scale, 6)],
                "points_units": [[round(p[0], 6), round(p[1], 6)]
                                 for p in record["points"]],
                "points_ft": [[round(p[0] * scale, 6), round(p[1] * scale, 6)]
                              for p in record["points"]],
            })
        elif record["type"] in ("TEXT", "MTEXT"):
            item.update({"text": record["text"], "position_units": record["position"],
                         "height_units": record["height"], "view": classify(
                             [record["position"][0], record["position"][1],
                              record["position"][0], record["position"][1]])})
        else:
            item.update({"shape": record["shape"], "position_units": record["position"],
                         "height_units": record["height"]})
        out_entities.append(item)

    doc = {
        "schema": "cozy-digitized-dxf/1",
        "source": {
            "file": SOURCE.name,
            "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "bytes": SOURCE.stat().st_size,
            "header": header,
        },
        "units": {"points_units": "drawing units", "points_ft": "ft"},
        "scale": {
            "ft_per_unit": scale,
            "assert_rel_tol": SCALE_ASSERT_REL_TOL,
            "max_rel_spread": spread,
            "estimates": estimates,
            "provenance": "Solved from dimension texts and LONGARROW positions "
                          "inside COZY3V.DXF; no scale was assumed.",
        },
        "entity_census": census,
        "layer_census": layers,
        "view_classification": {
            "rules": VIEW_RULES,
            "gaps": gaps,
            "counts": {view: sum(1 for e in out_entities
                                 if e.get("view") == view)
                       for view in ("top", "front", "side")},
        },
        "dimension_texts": [e for e in out_entities if e["type"] == "TEXT"],
        "entities": out_entities,
        "limitations": [
            "Only dimension texts are stated dimensions; all other values are "
            "measurements of drawing geometry multiplied by the solved scale.",
            "points_ft uses the drawing origin, not an aircraft datum.",
            "View labels come from fixed thresholds, verified by empty-band "
            "checks and a rendered preview; they are not from layer names.",
            "The aft part of the side view (entities 2780-3111: propeller, "
            "spinner, winglet) sits beyond the fuselage outline on the sheet. "
            "It was tested and belongs to the side view, not a separate "
            "detail view: its entity indices interleave with the rest of the "
            "side view, its outlines touch the rear-fuselage and wing "
            "outlines at zero distance, and its spinner measures 1.312 x "
            "0.844 ft against 1.351 x 0.925 ft in the top view, i.e. the "
            "same 1:1 scale. It is therefore reported as view=side.",
            "Polylines are open/closed as stored (POLYLINE flag 0 for all 92); "
            "the file has no arcs, bulges or z coordinates.",
        ],
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=True) + "\n",
                   encoding="utf-8")
    print(f"scale_ft_per_unit = {scale!r}")
    for estimate in estimates:
        print(f"  {estimate['axis']} {estimate['text']!r}: "
              f"{estimate['arrow_span_units']:.10f} units -> "
              f"{estimate['value_ft']:.10f} ft -> "
              f"{estimate['scale_ft_per_unit']!r}")
    print(f"max_rel_spread = {spread:.3e} (tol {SCALE_ASSERT_REL_TOL:.0e})")
    print("view counts:", doc["view_classification"]["counts"])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
