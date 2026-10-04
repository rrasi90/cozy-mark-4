#!/usr/bin/env python3
"""Build the referenced dimension table for COZY Mark IV.

Reads the digitised three-view record (``COZY3V_digitized.json``) produced by
``digitize_dxf.py`` and the parameter dictionary of
``Cozy_MKIV_OpenVSP_Baseline.py``, then writes:

* ``dimensions.json`` -- machine readable, schema ``cozy-dimensions/1``
* ``DIMENSIONS.md``   -- human readable table

Every drawing value carries provenance: source file, SHA-256, view, layer,
entity indices and the measurement method.  Nothing is inferred from memory.

Run (read only, no model side effects)::

    python measure_dxf.py
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DXF_NAME = "COZY3V.DXF"
DIGITIZED = HERE / "COZY3V_digitized.json"
BASELINE = HERE / "Cozy_MKIV_OpenVSP_Baseline.py"
OUT_JSON = HERE / "dimensions.json"
OUT_MD = HERE / "DIMENSIONS.md"
OUT_LOFT = HERE / "body_loft.json"

SCHEMA = "cozy-dimensions/1"
LOFT_SCHEMA = "cozy-body-loft/1"

# Tolerances: how far a model value may sit from the drawing value and still
# count as "match".  Lengths are tight because the digitisation is exact for
# the vectors; areas allow for the fact that the model wing is a simplified
# trapezoid.
TOLERANCE = {
    "ft": 0.05,
    "ft2": 0.5,
    "deg": 0.5,
    "ratio": 0.01,
}

# Layer / view of everything that belongs to the drawing outline itself.
OUTLINE_LAYER = "5"

# A polyline segment whose station span is no more than
# FACE_STATION_TOL and whose lateral span is at least
# FACE_WIDTH_FT is a drawn face (the fuselage tail face):
# its digitised corners sit a few thousandths of a foot
# apart in station, so the face must contribute both
# corners to the silhouette envelope.
FACE_STATION_TOL = 0.01
FACE_WIDTH_FT = 0.5

# The fuselage side view is drawn as three edge-adjacent outlines:
# 1927 forward body (nose to the wing/fillet junction), 2692 the
# turtledeck ramp between the canopy aft end and the fin base, and
# 2044 the aft body (fin and turtledeck down to the tail).  The plan
# view draws the fuselage as 678 (forward) and 457 (aft).  The outer
# silhouette of the body is the envelope of those outlines.
BODY_SIDE_OUTLINE = [1927, 2692, 2044]
BODY_PLAN_OUTLINE = [678, 457]

# Reference stations where the loft is checked section by section:
# the widest station, the nose-top peak, both ends of the turtledeck
# ramp, the aft-body junction (deepest belly, tallest section) and the
# tail.  The keys below are entity indices, not station numbers.
LOFT_REFERENCE_KEYS = {
    "widest": ("plan", 678),
    "nose_top_peak": ("side_max_z", 1927),
    "turtledeck_ramp_foot": ("station", 2692, "min"),
    "turtledeck_ramp_top": ("station", 2692, "max"),
    "aft_body_junction": ("side_min_z", 2044),
    "tail": ("length", None),
}


# --------------------------------------------------------------------------
# digitised geometry helpers
# --------------------------------------------------------------------------


class Drawing:
    def __init__(self, record: dict) -> None:
        self.record = record
        self.scale = float(record["scale"]["ft_per_unit"])
        self.sha256 = str(record["source"]["sha256"]).upper()
        self.entities = {int(e["index"]): e for e in record["entities"]}
        self.dimension_texts = record["scale"]["estimates"]

    # -- raw access -------------------------------------------------------
    def entity(self, index: int) -> dict:
        try:
            return self.entities[index]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"entity {index} missing from {DIGITIZED.name}") from exc

    def view(self, index: int) -> str:
        return str(self.entity(index).get("view"))

    def layer(self, index: int) -> str:
        return str(self.entity(index).get("layer"))

    def points(self, index: int) -> list[tuple[float, float]]:
        return [(float(p[0]), float(p[1])) for p in self.entity(index)["points_ft"]]

    def bbox(self, index: int) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.points(index)]
        ys = [p[1] for p in self.points(index)]
        return (min(xs), max(xs), min(ys), max(ys))

    def span_x(self, indices: list[int]) -> float:
        lo = min(self.bbox(i)[0] for i in indices)
        hi = max(self.bbox(i)[1] for i in indices)
        return hi - lo

    def span_y(self, indices: list[int]) -> float:
        lo = min(self.bbox(i)[2] for i in indices)
        hi = max(self.bbox(i)[3] for i in indices)
        return hi - lo

    def centre_x(self, indices: list[int]) -> float:
        lo = min(self.bbox(i)[0] for i in indices)
        hi = max(self.bbox(i)[1] for i in indices)
        return (lo + hi) / 2.0

    def area(self, index: int) -> float:
        pts = self.points(index)
        total = 0.0
        for k in range(len(pts)):
            x1, y1 = pts[k]
            x2, y2 = pts[(k + 1) % len(pts)]
            total += x1 * y2 - x2 * y1
        return abs(total) / 2.0

    def area_sum(self, indices: list[int]) -> float:
        return sum(self.area(i) for i in indices)

    def len_ft(self, index: int) -> float:
        """Euclidean length of a two point LINE."""
        pts = self.points(index)
        if len(pts) != 2:
            raise ValueError(f"LINE {index} has {len(pts)} points")
        return math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])

    # -- dimension texts ---------------------------------------------------
    def dimension_value(self, text_index: int) -> float:
        for est in self.dimension_texts:
            if int(est["text_index"]) == text_index:
                return float(est["value_ft"])
        raise KeyError(f"dimension text {text_index} not solved by digitiser")

    def arrow_span(self, text_index: int) -> float:
        for est in self.dimension_texts:
            if int(est["text_index"]) == text_index:
                arrows = est["arrows_units"]
                axis = est["axis"]
                k = 0 if axis == "x" else 1
                return abs(arrows[1][k] - arrows[0][k]) * self.scale
        raise KeyError(f"dimension text {text_index} not solved by digitiser")

    def arrow_indices(self, text_index: int) -> list[int]:
        for est in self.dimension_texts:
            if int(est["text_index"]) == text_index:
                return [int(i) for i in est["arrow_indices"]]
        raise KeyError(f"dimension text {text_index} not solved by digitiser")

    # -- datums ------------------------------------------------------------
    def side_ground_ft(self) -> float:
        """x of the explicit ground line of the side view (LINE 3217)."""
        return self.bbox(3217)[1]

    def front_ground_ft(self) -> float:
        """Lowest outline y of the front view = wheel contact plane."""
        return min(
            self.bbox(int(e["index"]))[2]
            for e in self.record["entities"]
            if e.get("view") == "front"
            and e.get("type") in ("POLYLINE", "LINE")
            and e.get("layer") == OUTLINE_LAYER
        )

    def nose_station_top_ft(self) -> float:
        return min(
            self.bbox(int(e["index"]))[2]
            for e in self.record["entities"]
            if e.get("view") == "top"
            and e.get("type") in ("POLYLINE", "LINE")
            and e.get("layer") == OUTLINE_LAYER
        )

    def nose_station_side_ft(self) -> float:
        return min(
            self.bbox(int(e["index"]))[2]
            for e in self.record["entities"]
            if e.get("view") == "side"
            and e.get("type") in ("POLYLINE", "LINE")
            and e.get("layer") == OUTLINE_LAYER
        )

    # -- view relative quantities -----------------------------------------
    def side_station(self, index: int) -> tuple[float, float]:
        nose = self.nose_station_side_ft()
        lo, hi = self.bbox(index)[2], self.bbox(index)[3]
        return (lo - nose, hi - nose)

    def side_height(self, index: int) -> tuple[float, float]:
        ground = self.side_ground_ft()
        x0, x1, _, _ = self.bbox(index)
        # side view: station axis = y, vertical axis = x (reversed)
        return (ground - x1, ground - x0)

    def front_height(self, index: int) -> tuple[float, float]:
        ground = self.front_ground_ft()
        _, _, y0, y1 = self.bbox(index)
        return (y0 - ground, y1 - ground)


# --------------------------------------------------------------------------
# fuselage silhouette envelope
# --------------------------------------------------------------------------


def _envelope_crossings(
    points: list[tuple[float, float]], station: float
) -> list[float]:
    """Value coordinates where a polyline meets the vertical line
    ``coord == station``.  The digitised polylines are stored closed
    (first vertex repeated at the end), so iterating consecutive
    vertex pairs walks the whole loop.  Segments that end exactly on
    the station count, which keeps vertical faces (the aft-body
    forward face) measurable at their own station.

    A segment that runs laterally -- nearly constant ``coord`` across
    a real width -- is a drawn face (the fuselage tail face is drawn
    this way).  Its digitised corners can sit a few thousandths of a
    foot apart in ``coord``, so a station line through the face would
    otherwise clip a single corner and read the width as zero.  Such
    a segment contributes both corners at every station it spans."""
    values: list[float] = []
    for a, b in zip(points, points[1:]):
        ca, va = a
        cb, vb = b
        if abs(cb - ca) < 1e-12:
            if abs(ca - station) < 1e-9:
                values.append(va)
                values.append(vb)
            continue
        if (
            abs(cb - ca) <= FACE_STATION_TOL
            and abs(vb - va) >= FACE_WIDTH_FT
        ):
            if (
                min(ca, cb) - FACE_STATION_TOL
                <= station
                <= max(ca, cb) + FACE_STATION_TOL
            ):
                values.append(va)
                values.append(vb)
            continue
        lo, hi = (ca, cb) if ca <= cb else (cb, ca)
        if lo - 1e-9 <= station <= hi + 1e-9:
            t = (station - ca) / (cb - ca)
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            values.append(va + t * (vb - va))
    return values


def side_silhouette(
    drawing: Drawing, station: float
) -> tuple[float, float]:
    """(lowest, highest) point of the side-view body envelope at
    ``station``, in feet above the side-view ground line."""
    nose = drawing.nose_station_side_ft()
    ground = drawing.side_ground_ft()
    heights: list[float] = []
    for index in BODY_SIDE_OUTLINE:
        pts = [
            (p[1] - nose, ground - p[0]) for p in drawing.points(index)
        ]
        heights.extend(_envelope_crossings(pts, station))
    if not heights:
        raise ValueError(
            f"no side-view body outline crosses station {station}"
        )
    return min(heights), max(heights)


def plan_silhouette(
    drawing: Drawing, station: float
) -> tuple[float, float]:
    """(inboard, outboard) lateral extent of the plan-view body
    envelope at ``station``, in raw plan-view x coordinates."""
    nose = drawing.nose_station_top_ft()
    laterals: list[float] = []
    for index in BODY_PLAN_OUTLINE:
        pts = [(p[1] - nose, p[0]) for p in drawing.points(index)]
        laterals.extend(_envelope_crossings(pts, station))
    if not laterals:
        raise ValueError(
            f"no plan-view body outline crosses station {station}"
        )
    return min(laterals), max(laterals)


def silhouette_extrema(drawing: Drawing) -> tuple[float, float]:
    """(lowest, highest) point of the side-view body silhouette.

    The envelope is piecewise linear with breakpoints only at
    outline vertices, so its extrema are attained at vertex
    stations and scanning those stations is exact.
    """
    nose = drawing.nose_station_side_ft()
    stations = sorted({
        p[1] - nose
        for index in BODY_SIDE_OUTLINE
        for p in drawing.points(index)
    })
    lows, highs = [], []
    for station in stations:
        low, high = side_silhouette(drawing, station)
        lows.append(low)
        highs.append(high)
    return min(lows), max(highs)


def _widest_plan_station(drawing: Drawing) -> float:
    """Station of the widest plan-view body section.  The width is
    piecewise linear between vertices, so the maximum is at a
    vertex station of either plan outline."""
    nose = drawing.nose_station_top_ft()
    stations = sorted({
        p[1] - nose
        for index in BODY_PLAN_OUTLINE
        for p in drawing.points(index)
    })
    best_station = 0.0
    best_width = -1.0
    for station in stations:
        lo, hi = plan_silhouette(drawing, station)
        if hi - lo > best_width:
            best_width = hi - lo
            best_station = station
    return best_station


def fuselage_profile_stations(drawing: Drawing, length: float) -> list[float]:
    """Uniform station grid plus the stations where the drawn
    silhouette changes slope or joins the next outline, so the
    loft follows the drawn contour instead of smoothing across
    the joints.  A feature station that lands within 1e-3 ft
    of a grid station replaces it: the section then carries
    the vertex value exactly, whereas a separate section that
    close would make the spline overshoot."""
    cells = 31  # ~0.45 ft
    merged = [k * length / cells for k in range(cells + 1)]
    nose_side = drawing.nose_station_side_ft()
    nose_top = drawing.nose_station_top_ft()

    def vertex_station(index: int, pick: str) -> float:
        pts = drawing.points(index)
        ground = drawing.side_ground_ft()
        heights = [ground - p[0] for p in pts]
        if pick == "max_z":
            return pts[heights.index(max(heights))][1] - nose_side
        if pick == "min_z":
            return pts[heights.index(min(heights))][1] - nose_side
        if pick == "min":
            return min(p[1] for p in pts) - nose_side
        if pick == "max":
            return max(p[1] for p in pts) - nose_side
        raise ValueError(f"unknown pick {pick!r}")

    keys = [
        _widest_plan_station(drawing),
        vertex_station(1927, "max_z"),
        vertex_station(2692, "min"),
        vertex_station(2692, "max_z"),
        vertex_station(2692, "max"),
        vertex_station(1927, "max"),
        vertex_station(2044, "min_z"),
        length,
    ]
    for key in keys:
        hits = [i for i, s in enumerate(merged) if abs(key - s) <= 1e-3]
        if hits:
            for i in hits:
                merged[i] = key
        else:
            merged.append(key)
    return sorted(merged)


def fuselage_profile(
    drawing: Drawing, stations: list[float]
) -> list[dict]:
    """Outer silhouette of the fuselage at each station: plan-view
    width and side-view top/bottom heights, above the ground line
    and from the plan-view nose."""
    sections: list[dict] = []
    for station in stations:
        low, high = side_silhouette(drawing, station)
        lat_lo, lat_hi = plan_silhouette(drawing, station)
        sections.append({
            "station_ft": round(station, 6),
            "half_width_ft": round((lat_hi - lat_lo) / 2.0, 6),
            "width_ft": round(lat_hi - lat_lo, 6),
            "centre_y_offset_ft": round((lat_hi + lat_lo) / 2.0, 6),
            "z_top_ft": round(high, 6),
            "z_bot_ft": round(low, 6),
            "height_ft": round(high - low, 6),
            "centre_z_ft": round((high + low) / 2.0, 6),
        })
    return sections


def loft_reference_stations(
    drawing: Drawing, profile: list[dict], length: float
) -> list[dict]:
    """The stations at which verify_geometry.py re-measures the
    model fuselage section width and height against the loft."""
    nose_side = drawing.nose_station_side_ft()
    ground = drawing.side_ground_ft()
    nose_peak = drawing.points(1927)
    peak_station = nose_peak[
        [ground - p[0] for p in nose_peak].index(
            max(ground - p[0] for p in nose_peak)
        )
    ][1] - nose_side

    def nearest(station: float) -> dict:
        return min(profile, key=lambda s: abs(s["station_ft"] - station))

    wanted = [
        ("widest", _widest_plan_station(drawing)),
        ("nose_top_peak", peak_station),
        ("turtledeck_ramp_foot",
         min(p[1] for p in drawing.points(2692)) - nose_side),
        ("turtledeck_ramp_top",
         max(p[1] for p in drawing.points(2692)) - nose_side),
        ("aft_body_junction",
         min(drawing.points(2044),
             key=lambda p: ground - p[0])[1] - nose_side),
        ("tail_face", length),
    ]
    refs = []
    for name, station in wanted:
        section = nearest(station)
        refs.append({
            "name": name,
            "station_ft": round(station, 6),
            "loft_station_ft": section["station_ft"],
            "width_ft": section["width_ft"],
            "height_ft": section["height_ft"],
        })
    return refs


# --------------------------------------------------------------------------
# model parameter access
# --------------------------------------------------------------------------


_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}


def _literal(node: ast.AST) -> object:
    """Evaluate literals plus simple numeric arithmetic such as ``138.0 / 12.0``."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _literal(node.operand)
        if not isinstance(value, (int, float)):
            raise ValueError(f"non numeric unary operand: {ast.dump(node)}")
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _literal(node.left)
        right = _literal(node.right)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ValueError(f"non numeric binary operand: {ast.dump(node)}")
        return _BINOPS[type(node.op)](left, right)
    raise ValueError(f"unsupported expression in P: {ast.dump(node)}")


def load_model_parameters(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "P":
                    if not isinstance(node.value, ast.Dict):
                        raise TypeError("P is not a dict literal")
                    keys = [_literal(k) for k in node.value.keys]
                    values = [_literal(v) for v in node.value.values]
                    return {str(k): v for k, v in zip(keys, values)}
    raise LookupError(f"no assignment to P found in {path.name}")


def as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


# --------------------------------------------------------------------------
# table rows
# --------------------------------------------------------------------------


def source(
    drawing: Drawing,
    view: str,
    entities: list[int],
    detail: str,
    layers: list[str] | None = None,
) -> dict:
    if layers is None:
        layers = sorted({drawing.layer(i) for i in entities})
    return {
        "file": DXF_NAME,
        "sha256": drawing.sha256,
        "view": view,
        "layers": layers,
        "entities": list(entities),
        "detail": detail,
    }


def build_rows(drawing: Drawing, model: dict, loft: dict) -> list[dict]:
    rows: list[dict] = []

    def add(
        row_id: str,
        label: str,
        unit: str,
        method: str,
        value: float,
        detail: str,
        src: dict,
        model_parameter: str | None = None,
        cross_checks: list[dict] | None = None,
        note: str | None = None,
    ) -> None:
        model_value = as_float(model.get(model_parameter)) if model_parameter else None
        tolerance = TOLERANCE[unit]
        if model_value is None:
            deviation = None
            status = "no-model-value"
        else:
            deviation = model_value - value
            status = "match" if abs(deviation) <= tolerance else "off"
        rows.append(
            {
                "id": row_id,
                "label": label,
                "unit": unit,
                "method": method,
                "drawing_value": round(value, 6),
                "tolerance": tolerance,
                "source": src,
                "cross_checks": cross_checks or [],
                "model_parameter": model_parameter,
                "model_value": None if model_value is None else round(model_value, 6),
                "deviation": None if deviation is None else round(deviation, 6),
                "status": status,
                "note": note,
            }
        )

    # -- stated dimensions (text + LONGARROW) -----------------------------
    add(
        "overall_length_ft",
        "Overall length, nose to aftmost winglet tip",
        "ft",
        "text-dimension",
        drawing.dimension_value(3292),
        "TEXT 3292 \"16' 11.00\"\" with LONGARROW pair; extension lines 3293-3296",
        source(
            drawing,
            "top",
            [3292, 3297, 3298, 3293, 3294, 3295, 3296],
            "Overall length dimension of the plan view.",
            layers=["5", "8"],
        ),
        model_parameter="overall_length",
        cross_checks=[
            {
                "label": "arrow span",
                "value_ft": round(drawing.arrow_span(3292), 6),
                "entities": drawing.arrow_indices(3292),
            },
            {
                "label": "top outline nose to winglet aft tip",
                "value_ft": round(
                    max(drawing.bbox(i)[3] for i in (951, 1059))
                    - drawing.nose_station_top_ft(),
                    6,
                ),
                "entities": [678, 951, 1059],
            },
        ],
        note=(
            "The model reports overall_length but no geometry is driven by it; "
            "the modelled overall length is fuselage length plus winglet overhang."
        ),
    )

    add(
        "overall_span_ft",
        "Overall span, winglet tip to winglet tip",
        "ft",
        "text-dimension",
        drawing.dimension_value(3278),
        "TEXT 3278 \"28' 1.50\"\" with LONGARROW pair 3283/3284; extension lines 3279-3282",
        source(
            drawing,
            "top",
            [3278, 3283, 3284, 3279, 3280, 3281, 3282],
            "Span dimension of the plan view.",
            layers=["5", "8"],
        ),
        model_parameter="main_span",
        cross_checks=[
            {
                "label": "top-view arrow span",
                "value_ft": round(drawing.arrow_span(3278), 6),
                "entities": drawing.arrow_indices(3278),
            },
            {
                "label": "front-view dimension 3285",
                "value_ft": round(drawing.dimension_value(3285), 6),
                "entities": [3285, 3290, 3291],
            },
            {
                "label": "front-view outline extent (winglets 1355/1458)",
                "value_ft": round(drawing.span_x([1355, 1458]), 6),
                "entities": [1355, 1458],
            },
            {
                "label": "top-view outline extent (wing panels 927/1035)",
                "value_ft": round(drawing.span_x([927, 1035]), 6),
                "entities": [927, 1035],
            },
            {
                "label": "front-view wing panel band (1385/1488)",
                "value_ft": round(drawing.span_x([1385, 1488]), 6),
                "entities": [1385, 1488],
            },
        ],
        note=(
            "The wing panel band of the front view stops 0.19 ft inboard of the "
            "dimensioned extremity; the winglet outline reaches it. The plan view "
            "wing panels reach the same extremity."
        ),
    )

    # -- planform areas (top view, polyline-measured) ----------------------
    wing_panels = [927, 1035]
    ailerons = [974, 1082]
    strakes = [514, 596]
    canard_main = [410]
    elevators = [1089, 1096]

    add(
        "main_planform_area_ft2",
        "Main wing planform area, wing panels plus strakes plus aileron strips",
        "ft2",
        "polyline-measured",
        drawing.area_sum(wing_panels + ailerons + strakes),
        "Union of outlines 927/1035 (panels), 974/1082 (aileron strips filling the "
        "panel notches), 514/596 (strakes); outlines share edges, no overlap.",
        source(
            drawing,
            "top",
            wing_panels + ailerons + strakes,
            "Sum of shoelace areas of six edge-adjacent closed outlines.",
        ),
        model_parameter="main_area",
        cross_checks=[
            {
                "label": "wing panels only",
                "value_ft2": round(drawing.area_sum(wing_panels), 6),
                "entities": wing_panels,
            },
            {
                "label": "aileron strips only",
                "value_ft2": round(drawing.area_sum(ailerons), 6),
                "entities": ailerons,
            },
            {
                "label": "strakes only",
                "value_ft2": round(drawing.area_sum(strakes), 6),
                "entities": strakes,
            },
        ],
        note=(
            "The drawn strakes stop at the fuselage sides, so the centre strip "
            "under the fuselage is not drawn. The model main wing is a single "
            "full-span trapezoid of equal total area; the shapes are not identical."
        ),
    )

    add(
        "canard_planform_area_ft2",
        "Canard planform area including elevators",
        "ft2",
        "polyline-measured",
        drawing.area_sum(canard_main + elevators),
        "Outline 410 plus elevator strips 1089/1096 drawn just aft of the trailing edge.",
        source(
            drawing,
            "top",
            canard_main + elevators,
            "Sum of shoelace areas; the elevator strips do not overlap outline 410.",
        ),
        model_parameter="canard_area",
        cross_checks=[
            {
                "label": "canard panel only",
                "value_ft2": round(drawing.area_sum(canard_main), 6),
                "entities": canard_main,
            }
        ],
    )

    # -- planform linear (top view) ---------------------------------------
    add(
        "canard_span_ft",
        "Canard span",
        "ft",
        "polyline-measured",
        drawing.span_x([410]),
        "Outline 410, x extent of the canard plan.",
        source(drawing, "top", [410], "Max x minus min x of the canard outline."),
        model_parameter="canard_span",
        cross_checks=[
            {
                "label": "front-view canard panels 1399/1344/1502",
                "value_ft": round(drawing.span_x([1399, 1344, 1502]), 6),
                "entities": [1399, 1344, 1502],
            }
        ],
        note="Front view stops short of the plan view by the rounded canard tips.",
    )

    add(
        "canard_le_from_nose_ft",
        "Canard leading edge station from nose",
        "ft",
        "polyline-measured",
        drawing.bbox(410)[2] - drawing.nose_station_top_ft(),
        "Min y of canard outline 410 minus min y of fuselage outline 678.",
        source(
            drawing,
            "top",
            [410, 678],
            "Both outlines on layer 5 of the plan view; station axis is +y aft.",
        ),
        model_parameter="canard_x",
        cross_checks=[
            {
                "label": "side-view canard 2737 station range",
                "value_ft": [
                    round(v, 6) for v in drawing.side_station(2737)
                ],
                "entities": [2737],
            }
        ],
    )

    add(
        "canard_le_sweep_deg",
        "Canard leading edge sweep",
        "deg",
        "polyline-measured",
        _sweep_deg(
            drawing.points(410)[14],
            drawing.points(410)[15],
        ),
        "Leading edge of outline 410 runs from (16.424, 14.231) to (27.882, 14.231), "
        "constant y.",
        source(drawing, "top", [410], "Straight leading edge segment of the canard."),
        model_parameter="canard_le_sweep_deg",
        note="The model sets Sweep XSec_1 of the canard to 0.0 directly.",
    )

    add(
        "canard_taper",
        "Canard taper ratio",
        "ratio",
        "polyline-measured",
        _canard_taper(drawing),
        "Chord on the outboard end divided by chord on the inboard end of the "
        "straight leading edge 410 and the two elevator trailing edges 1089/1096.",
        source(
            drawing,
            "top",
            [410, 1089, 1096],
            "Both leading edge and elevator trailing edge are straight and "
            "constant in y, so the idealised canard trapezoid is rectangular.",
        ),
        model_parameter="canard_taper",
        note=(
            "The drawn tips are rounded, so the panel plus elevator shoelace "
            "area is smaller than a true rectangle; the model keeps the span and "
            "area drivers and the rectangular shape."
        ),
    )

    add(
        "canard_max_chord_ft",
        "Canard maximum chord",
        "ft",
        "polyline-measured",
        drawing.span_y([410] + elevators),
        "y extent of outline 410 plus elevator strips 1089/1096.",
        source(
            drawing,
            "top",
            [410] + elevators,
            "Max y minus min y of canard and elevator outlines.",
        ),
        model_parameter=None,
    )

    add(
        "main_le_sweep_deg",
        "Main wing leading edge sweep",
        "deg",
        "polyline-measured",
        _sweep_deg(
            drawing.points(927)[1],
            drawing.points(927)[2],
        ),
        "Leading edge of left panel 927, root point (16.424, 22.268) to tip point "
        "(8.504, 25.401).",
        source(
            drawing,
            "top",
            [927, 1035],
            "Angle of the straight leading edge segment measured from the span axis.",
        ),
        model_parameter="main_le_sweep_deg",
        cross_checks=[
            {
                "label": "right panel 1035",
                "value_deg": round(
                    _sweep_deg(drawing.points(1035)[2], drawing.points(1035)[1]), 6
                ),
                "entities": [1035],
            }
        ],
        note="The baseline wing is built with Sweep XSec_1 = 0.",
    )

    add(
        "main_wing_taper",
        "Main wing taper ratio",
        "ratio",
        "polyline-measured",
        _main_taper(drawing),
        "Tip chord divided by root chord of the idealised trapezoid built from "
        "the straight leading edge 1/2 and trailing edge 15/14 of panel 927.",
        source(
            drawing,
            "top",
            [927, 1035],
            "Both edge lines extrapolated to the centreline and to the half-span.",
        ),
        model_parameter="main_taper",
        cross_checks=[
            {
                "label": "root chord",
                "value_ft": round(_main_root_chord(drawing), 6),
                "entities": [927, 1035],
            },
            {
                "label": "tip chord at the half-span",
                "value_ft": round(_tip_chord(drawing), 6),
                "entities": [927, 1035],
            },
        ],
        note=(
            "The model wing is a single full-span trapezoid driven by span and "
            "area, so root and tip chord follow from the taper ratio."
        ),
    )

    add(
        "main_root_le_from_nose_ft",
        "Main wing leading edge station at the centreline",
        "ft",
        "polyline-measured",
        _root_le_station(drawing),
        "Leading edge line of panel 927 extrapolated to the plan centreline.",
        source(
            drawing,
            "top",
            [927, 1035, 678],
            "Swept leading edge line extended to the centreline x of the plan view.",
        ),
        model_parameter="wing_x",
        note=(
            "The drawn panels start at the strake junction, so the centreline "
            "leading edge is an extrapolation of the outer panel leading edge."
        ),
    )

    add(
        "main_tip_chord_ft",
        "Main wing tip chord",
        "ft",
        "polyline-measured",
        _tip_chord(drawing),
        "Chord of the idealised trapezoid at the half-span station, from the "
        "straight leading and trailing edge segments of outline 927.",
        source(drawing, "top", [927, 1035], "Tip corner points of the wing outline."),
        model_parameter=None,
        note=(
            "The panel is cut along the rounded wing tip, so the drawn tip edge "
            "is a diagonal longer than the local chord; the local chord is used "
            "here. The model derives root and tip chord from the SPAN/AREA/TAPER "
            "driver group, so no independent tip chord parameter exists."
        ),
    )

    add(
        "fuselage_length_ft",
        "Fuselage length, nose to tail",
        "ft",
        "polyline-measured",
        drawing.bbox(457)[3] - drawing.nose_station_top_ft(),
        "Tail outline 457 max y minus nose outline 678 min y.",
        source(
            drawing,
            "top",
            [678, 457],
            "Forward and aft fuselage outlines of the plan view.",
        ),
        model_parameter="fuselage_length",
        cross_checks=[
            {
                "label": "side view outline 1927 + 2044",
                "value_ft": round(
                    drawing.side_station(2044)[1] - drawing.side_station(1927)[0], 6
                ),
                "entities": [1927, 2044],
            }
        ],
    )

    add(
        "fuselage_max_width_ft",
        "Fuselage maximum width",
        "ft",
        "polyline-measured",
        drawing.span_x([678]),
        "x extent of fuselage outline 678 in the plan view.",
        source(drawing, "top", [678], "Max x minus min x of the forward fuselage outline."),
        model_parameter="fuselage_max_dia",
        cross_checks=[
            {
                "label": "front-view fuselage section 1148",
                "value_ft": round(drawing.span_x([1148]), 6),
                "entities": [1148],
            }
        ],
    )

    add(
        "spinner_length_ft",
        "Spinner length",
        "ft",
        "polyline-measured",
        drawing.span_y([478]),
        "y extent of spinner outline 478 in the plan view.",
        source(drawing, "top", [478], "Max y minus min y of the spinner outline."),
        model_parameter="spinner_length",
        cross_checks=[
            {
                "label": "side view spinner 3032",
                "value_ft": round(drawing.side_station(3032)[1] - drawing.side_station(3032)[0], 6),
                "entities": [3032],
            }
        ],
    )

    add(
        "spinner_diameter_ft",
        "Spinner diameter",
        "ft",
        "polyline-measured",
        drawing.span_x([478]),
        "x extent of spinner outline 478 in the plan view.",
        source(drawing, "top", [478], "Max x minus min x of the spinner outline."),
        model_parameter="spinner_diameter",
        cross_checks=[
            {
                "label": "side view spinner 3032 height",
                "value_ft": round(
                    drawing.side_height(3032)[1] - drawing.side_height(3032)[0], 6
                ),
                "entities": [3032],
            }
        ],
    )

    add(
        "winglet_plan_length_ft",
        "Winglet chordwise length in plan",
        "ft",
        "polyline-measured",
        drawing.span_y([951, 1059]),
        "y extent of winglet plan outlines 951/1059.",
        source(
            drawing,
            "top",
            [951, 1059],
            "Max y minus min y of the two winglet plan projections.",
        ),
        model_parameter=None,
        cross_checks=[
            {
                "label": "side view winglet 2925",
                "value_ft": round(
                    drawing.side_station(2925)[1] - drawing.side_station(2925)[0], 6
                ),
                "entities": [2925],
            }
        ],
    )

    winglet_plan_le = (
        min(drawing.bbox(i)[2] for i in (951, 1059))
        - drawing.nose_station_top_ft()
    )
    winglet_plan_te = (
        max(drawing.bbox(i)[3] for i in (951, 1059))
        - drawing.nose_station_top_ft()
    )

    add(
        "winglet_le_from_nose_ft",
        "Winglet root leading edge station",
        "ft",
        "polyline-measured",
        winglet_plan_le,
        "Forward station of winglet plan outlines 951/1059, from the plan nose "
        "outline 678.",
        source(
            drawing,
            "top",
            [678, 951, 1059],
            "Min y of the winglet plan projections minus the nose station.",
        ),
        model_parameter="winglet_le_station",
        cross_checks=[
            {
                "label": "main wing tip leading edge at the half-span",
                "value_ft": round(_main_trapezoid(drawing)["tip_le"], 6),
                "entities": [927, 1035],
            },
            {
                "label": "side view winglet leading edge at the wing plane",
                "value_ft": round(
                    _winglet_side_stations(drawing)[0], 6
                ),
                "entities": [2925, 2085, 3217],
            },
        ],
        note=(
            "The winglet sits aft of the wing tip leading edge; the setback is "
            f"{winglet_plan_le - _main_trapezoid(drawing)['tip_le']:.6f} ft."
        ),
    )

    add(
        "winglet_aft_station_ft",
        "Winglet aftmost station",
        "ft",
        "polyline-measured",
        winglet_plan_te,
        "Aft station of winglet plan outlines 951/1059, from the plan nose "
        "outline 678.",
        source(
            drawing,
            "top",
            [678, 951, 1059],
            "Max y of the winglet plan projections minus the nose station.",
        ),
        model_parameter="winglet_aft_station",
        cross_checks=[
            {
                "label": "dimensioned overall length",
                "value_ft": round(drawing.dimension_value(3292), 6),
                "entities": [3292, 3297, 3298],
            },
            {
                "label": "side view winglet 2925 aft station",
                "value_ft": round(drawing.side_station(2925)[1], 6),
                "entities": [2925],
            },
        ],
        note="This is the aftmost point of the whole airframe and therefore "
        "sets the modelled overall length.",
    )

    add(
        "winglet_taper",
        "Winglet taper ratio",
        "ratio",
        "polyline-measured",
        _winglet_taper(drawing),
        "Chord at the wing plane divided by chord at the winglet tip, from the "
        "straight leading and trailing edge segments of side-view outline 2925.",
        source(
            drawing,
            "side",
            [2925, 2085, 3217, 1355],
            "Leading edge points 18->17 and trailing edge points 101->102 "
            "extrapolated to the wing plane and to the front-view tip height.",
        ),
        model_parameter="winglet_taper",
        note=(
            "The side view winglet root chord is 0.05 ft longer than the main "
            "wing tip chord drawn in plan; the model root chord follows the wing."
        ),
    )

    # -- front view heights ------------------------------------------------
    winglet_h = drawing.front_height(1355)[1] - drawing.front_height(1355)[0]
    side_winglet_h = (
        drawing.side_height(2925)[1] - drawing.side_height(2925)[0]
    )
    add(
        "winglet_height_ft",
        "Winglet height above the wing",
        "ft",
        "polyline-measured",
        winglet_h,
        "Vertical extent of front-view winglet outlines 1355/1458 above the "
        "front-view contact plane.",
        source(
            drawing,
            "front",
            [1355, 1458],
            "Max y minus min y of the winglet outlines in the front view.",
        ),
        model_parameter="winglet_height",
        cross_checks=[
            {
                "label": "side view winglet 2925",
                "value_ft": round(side_winglet_h, 6),
                "entities": [2925],
            },
            {
                "label": "front view height of winglet base",
                "value_ft": round(drawing.front_height(1355)[0], 6),
                "entities": [1355],
            },
        ],
        note=(
            "Front and side views disagree on the winglet height by "
            f"{abs(side_winglet_h - winglet_h):.3f} ft; the front view is used "
            "because it shows the winglet full height without foreshortening."
        ),
    )

    add(
        "canard_center_height_ft",
        "Canard centre height above ground",
        "ft",
        "polyline-measured",
        _mid(drawing.side_height(2737)),
        "Mid height of side-view canard outline 2737 above the explicit ground "
        "line 3217.",
        source(
            drawing,
            "side",
            [2737, 3217],
            "Ground datum is LINE 3217, the wheels of the side view rest on it.",
        ),
        model_parameter="canard_z",
        cross_checks=[
            {
                "label": "front view canard 1399/1344/1502",
                "value_ft": round(
                    _mid(
                        (
                            min(drawing.front_height(i)[0] for i in (1399, 1344, 1502)),
                            max(drawing.front_height(i)[1] for i in (1399, 1344, 1502)),
                        )
                    ),
                    6,
                ),
                "entities": [1399, 1344, 1502],
            }
        ],
        note="Front view sits higher than the side view; the side view carries the "
        "explicit ground line and is used as the height datum.",
    )

    add(
        "wing_center_height_ft",
        "Main wing centre height above ground",
        "ft",
        "polyline-measured",
        _mid(drawing.side_height(2085)),
        "Mid height of side-view wing outline 2085 above ground line 3217.",
        source(
            drawing,
            "side",
            [2085, 3217],
            "Wing outline of the side view; ground datum LINE 3217.",
        ),
        model_parameter="wing_z",
        cross_checks=[
            {
                "label": "front view wing band 1385/1488",
                "value_ft": round(
                    _mid(
                        (
                            min(drawing.front_height(i)[0] for i in (1385, 1488)),
                            max(drawing.front_height(i)[1] for i in (1385, 1488)),
                        )
                    ),
                    6,
                ),
                "entities": [1385, 1488],
            }
        ],
    )

    prop_lo = min(
        drawing.side_height(i)[0] for i in (2780, 2786)
    )
    prop_hi = max(drawing.side_height(i)[1] for i in (2780, 2786))
    add(
        "prop_center_height_ft",
        "Propeller centre height above ground",
        "ft",
        "polyline-measured",
        (prop_lo + prop_hi) / 2.0,
        "Mid height of side-view propeller blade outlines 2780/2786 above "
        "ground line 3217.",
        source(
            drawing,
            "side",
            [2780, 2786, 3217],
            "Blade outlines bound the propeller disc; ground datum LINE 3217.",
        ),
        model_parameter="prop_z",
        cross_checks=[
            {
                "label": "side view spinner 3032 centre",
                "value_ft": round(_mid(drawing.side_height(3032)), 6),
                "entities": [3032],
            }
        ],
    )

    add(
        "prop_diameter_ft",
        "Propeller diameter",
        "ft",
        "polyline-measured",
        prop_hi - prop_lo,
        "Vertical extent of side-view blade outlines 2780 (upper) and 2786 (lower).",
        source(
            drawing,
            "side",
            [2780, 2786],
            "Outer radii of both blades about the disc centre give the diameter.",
        ),
        model_parameter="prop_diameter",
        cross_checks=[
            {
                "label": "blade gap at hub (inner radii)",
                "value_ft": round(
                    drawing.side_height(2780)[0] - drawing.side_height(2786)[1], 6
                ),
                "entities": [2780, 2786],
            }
        ],
        note="The baseline hard-coded the propeller disk diameter at 5.80 ft.",
    )

    add(
        "prop_station_from_nose_ft",
        "Propeller disc station from nose",
        "ft",
        "polyline-measured",
        _prop_station(drawing),
        "Mid station of side-view blade outlines 2780/2786 measured from the "
        "side-view nose.",
        source(
            drawing,
            "side",
            [2780, 2786],
            "Axial extent of both blade outlines about the disc plane.",
        ),
        model_parameter="prop_x",
        cross_checks=[
            {
                "label": "side view spinner 3032 forward station",
                "value_ft": round(drawing.side_station(3032)[0], 6),
                "entities": [3032],
            },
            {
                "label": "side view spinner 3032 aft station",
                "value_ft": round(drawing.side_station(3032)[1], 6),
                "entities": [3032],
            },
            {
                "label": "top view spinner 478 forward station",
                "value_ft": round(
                    drawing.bbox(478)[2] - drawing.nose_station_top_ft(), 6
                ),
                "entities": [478],
            },
            {
                "label": "top view spinner 478 aft station",
                "value_ft": round(
                    drawing.bbox(478)[3] - drawing.nose_station_top_ft(), 6
                ),
                "entities": [478],
            },
        ],
        note=(
            "Station origins are per view: each view is referenced to its own nose "
            "outline, so the raw sheet coordinates are not comparable. After that "
            "correction the views still disagree slightly - the spinner forward "
            "station differs by 0.018 ft and the canard leading edge by 0.061 ft "
            "between the plan and side views - so longitudinal stations carry about "
            "+/-0.05 ft of inter-view uncertainty. This row uses the side view "
            "because the propeller disc is only drawn there."
        ),
    )

    add(
        "canopy_top_height_ft",
        "Canopy top height above ground",
        "ft",
        "polyline-measured",
        drawing.side_height(2177)[1],
        "Top of side-view canopy outline 2177 above ground line 3217.",
        source(drawing, "side", [2177, 3217], "Canopy outline of the side view."),
        model_parameter=None,
        cross_checks=[
            {
                "label": "front view canopy 1602",
                "value_ft": round(drawing.front_height(1602)[1], 6),
                "entities": [1602],
            }
        ],
    )

    add(
        "fuselage_center_height_ft",
        "Fuselage centre height above ground",
        "ft",
        "polyline-measured",
        loft["centre_z_ft"],
        "Mid-height of the full side-view fuselage silhouette: the "
        f"lowest belly point of outline 2044 ({loft['min_z_ft']:.6f} ft) "
        f"and the highest turtledeck point of outline 2692 "
        f"({loft['max_z_ft']:.6f} ft), averaged.",
        source(
            drawing,
            "side",
            BODY_SIDE_OUTLINE,
            "Envelope of the three side-view body outlines; the "
            "centre height is the mid-height of that envelope.",
        ),
        model_parameter="fuselage_z",
        cross_checks=[
            {
                "label": "forward fuselage 1927 mid height",
                "value_ft": round(_mid(drawing.side_height(1927)), 6),
                "entities": [1927],
            },
            {
                "label": "rear fuselage 2044 mid height",
                "value_ft": round(_mid(drawing.side_height(2044)), 6),
                "entities": [2044],
            },
            {
                "label": "front view fuselage section 1148",
                "value_ft": round(_mid(drawing.front_height(1148)), 6),
                "entities": [1148],
            },
        ],
        note=(
            "The fuselage is lofted from the side-view silhouette of "
            "outlines 1927 (forward body), 2692 (turtledeck ramp) and "
            "2044 (aft body), so the model centre height is the "
            "mid-height of the whole silhouette, not of the forward "
            "body alone. The three outline mid heights span "
            f"{_mid(drawing.side_height(1927)):.4f} to "
            f"{_mid(drawing.side_height(2044)):.4f} ft and the front "
            "view section 1148 sits "
            f"{abs(_mid(drawing.front_height(1148)) - loft['centre_z_ft']):.3f} "
            "ft from the side-view silhouette centre; the side view "
            "carries the explicit ground line and is the height datum."
        ),
    )

    # -- fuselage section reference stations (loft checks) --------
    for ref in loft["references"]:
        station = ref["station_ft"]
        label = f"at station {station:.4f} ft from the nose"
        add(
            f"fuselage_section_width_st_{station:.2f}_ft",
            f"Fuselage section width, station {station:.2f} ft",
            "ft",
            "polyline-measured",
            ref["width_ft"],
            f"Width of the plan-view body envelope of outlines "
            f"{BODY_PLAN_OUTLINE[0]}/{BODY_PLAN_OUTLINE[1]} {label}.",
            source(
                drawing,
                "top",
                BODY_PLAN_OUTLINE,
                f"Envelope of plan outlines {BODY_PLAN_OUTLINE[0]} and "
                f"{BODY_PLAN_OUTLINE[1]} at station {station:.6f} ft.",
            ),
            model_parameter=None,
            note=(
                "Reference station for the plan-derived fuselage loft; "
                "verify_geometry.py re-measures the model section width "
                "at this station against body_loft.json."
            ),
        )
        add(
            f"fuselage_section_height_st_{station:.2f}_ft",
            f"Fuselage section height, station {station:.2f} ft",
            "ft",
            "polyline-measured",
            ref["height_ft"],
            f"Height of the side-view body envelope of outlines "
            f"{'/'.join(str(i) for i in BODY_SIDE_OUTLINE)} {label}.",
            source(
                drawing,
                "side",
                BODY_SIDE_OUTLINE,
                f"Envelope of side outlines "
                f"{', '.join(str(i) for i in BODY_SIDE_OUTLINE)} at "
                f"station {station:.6f} ft.",
            ),
            model_parameter=None,
            note=(
                "Reference station for the plan-derived fuselage loft; "
                "verify_geometry.py re-measures the model section height "
                "at this station against body_loft.json."
            ),
        )

    # -- side view wheel geometry (reference only) -------------------------
    add(
        "nose_wheel_diameter_ft",
        "Nose wheel diameter",
        "ft",
        "polyline-measured",
        drawing.side_height(2458)[1] - drawing.side_height(2458)[0],
        "Vertical extent of side-view nose wheel outline 2458 above ground line 3217.",
        source(drawing, "side", [2458, 3217], "Nose wheel outline of the side view."),
        model_parameter="nose_wheel_diameter",
        cross_checks=[
            {
                "label": "front view nose wheel 1254",
                "value_ft": round(
                    drawing.front_height(1254)[1] - drawing.front_height(1254)[0], 6
                ),
                "entities": [1254],
            }
        ],
        note=(
            "The model gear placeholders are wheel-envelope pods sized by this "
            "diameter and resting on the ground datum; they are not a landing-gear model."
        ),
    )

    add(
        "main_wheel_diameter_ft",
        "Main wheel diameter",
        "ft",
        "polyline-measured",
        drawing.side_height(2625)[1] - drawing.side_height(2625)[0],
        "Vertical extent of side-view main wheel outline 2625 above ground line 3217.",
        source(drawing, "side", [2625, 3217], "Main wheel outline of the side view."),
        model_parameter="main_wheel_diameter",
        cross_checks=[
            {
                "label": "front view main wheel 1788",
                "value_ft": round(
                    drawing.front_height(1788)[1] - drawing.front_height(1788)[0], 6
                ),
                "entities": [1788],
            }
        ],
        note=(
            "The model gear placeholders are wheel-envelope pods sized by this "
            "diameter and resting on the ground datum; they are not a landing-gear model."
        ),
    )

    add(
        "main_gear_track_ft",
        "Main gear track, wheel centre to wheel centre",
        "ft",
        "polyline-measured",
        abs(drawing.centre_x([1788]) - drawing.centre_x([1109])),
        "Centre x of front-view main wheel outlines 1109 and 1788.",
        source(
            drawing,
            "front",
            [1109, 1788],
            "Difference of the wheel outline centre positions in the front view.",
        ),
        model_parameter="main_gear_track",
        note=(
            "The model main-gear placeholders are placed at plus/minus half of this "
            "track and rest on the ground datum; they are not a landing-gear model."
        ),
    )

    return rows


# --------------------------------------------------------------------------
# small geometry helpers used by the rows
# --------------------------------------------------------------------------


def _mid(interval: tuple[float, float]) -> float:
    return (interval[0] + interval[1]) / 2.0


def _sweep_deg(root: tuple[float, float], tip: tuple[float, float]) -> float:
    dx = tip[0] - root[0]
    dy = tip[1] - root[1]
    return math.degrees(math.atan2(abs(dy), abs(dx)))


def _root_le_station(drawing: Drawing) -> float:
    """Leading edge line of the left panel extrapolated to the plan centreline."""
    pts = drawing.points(927)
    root, tip = pts[1], pts[2]
    nose = drawing.nose_station_top_ft()
    centre = drawing.centre_x([927, 1035])
    slope = (tip[1] - root[1]) / (tip[0] - root[0])
    y_at_centre = root[1] + slope * (centre - root[0])
    return y_at_centre - nose


def _main_trapezoid(drawing: Drawing) -> dict:
    """Idealised main-wing trapezoid, in stations measured from the nose.

    Panel 927 is cut along the rounded wing tip, so neither its leading nor
    its trailing edge is a single straight segment end to end.  The two straight
    segments that bound the real lifting surface are the leading edge
    (points 1 -> 2) and the inboard part of the trailing edge (points 15 -> 14);
    points 16 and 17 belong to the aileron/elevator cut-out.  Both lines are
    extrapolated to the centreline and to the half-span, which is exactly how
    OpenVSP lays out its trapezoidal driver group.
    """
    pts = drawing.points(927)
    centre = drawing.centre_x([927, 1035])
    half = drawing.span_x([927, 1035]) / 2.0
    nose = drawing.nose_station_top_ft()
    le_root, le_tip = pts[1], pts[2]
    te_root, te_tip = pts[15], pts[14]
    le_slope = (le_tip[1] - le_root[1]) / (le_tip[0] - le_root[0])
    te_slope = (te_tip[1] - te_root[1]) / (te_tip[0] - te_root[0])

    def sta(line_point, slope, half_station):
        x = centre - half_station
        return line_point[1] + slope * (x - line_point[0]) - nose

    return {
        "root_le": sta(le_root, le_slope, 0.0),
        "root_te": sta(te_root, te_slope, 0.0),
        "tip_le": sta(le_root, le_slope, half),
        "tip_te": sta(te_root, te_slope, half),
        "half_span": half,
        "le_entities": [927, 1035],
        "te_entities": [927, 1035],
    }


def _main_root_chord(drawing: Drawing) -> float:
    t = _main_trapezoid(drawing)
    return t["root_te"] - t["root_le"]


def _tip_chord(drawing: Drawing) -> float:
    """Tip chord of the idealised trapezoid at the half-span station."""
    t = _main_trapezoid(drawing)
    return t["tip_te"] - t["tip_le"]


def _main_taper(drawing: Drawing) -> float:
    t = _main_trapezoid(drawing)
    return (t["tip_te"] - t["tip_le"]) / (t["root_te"] - t["root_le"])


def _canard_taper(drawing: Drawing) -> float:
    """The drawn canard has a straight unswept leading edge and a straight
    trailing edge shared with the two elevator strips, so its idealised
    trapezoid is rectangular and the taper ratio is 1.0."""
    le_inboard = drawing.points(410)[14][1]
    le_outboard = drawing.points(410)[15][1]
    te_inboard = drawing.bbox(1089)[3]
    te_outboard = drawing.bbox(1096)[3]
    return (te_outboard - le_outboard) / (te_inboard - le_inboard)


def _winglet_side_chord(drawing: Drawing, height: float) -> tuple[float, float]:
    """Leading and trailing edge stations of the side-view winglet at `height`.

    The side view uses y for the station axis and x for height, reversed about
    the explicit ground line, so a height h sits at x = ground - h.
    """
    ground = drawing.side_ground_ft()
    nose = drawing.nose_station_side_ft()
    pts = drawing.points(2925)
    le_root, le_tip = pts[18], pts[17]
    te_root, te_tip = pts[101], pts[102]

    def sta(point_a, point_b):
        slope = (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
        x = ground - height
        return point_a[1] + slope * (x - point_a[0]) - nose

    return sta(le_root, le_tip), sta(te_root, te_tip)


def _winglet_side_stations(drawing: Drawing) -> tuple[float, float]:
    """Leading and trailing edge stations of the side-view winglet base."""
    return _winglet_side_chord(drawing, _mid(drawing.side_height(2085)))


def _winglet_taper(drawing: Drawing) -> float:
    """Winglet taper from the straight leading/trailing edge segments of the
    side view, evaluated at the wing plane and at the winglet tip height."""
    wing_z = _mid(drawing.side_height(2085))
    tip_h = wing_z + (
        drawing.front_height(1355)[1] - drawing.front_height(1355)[0]
    )
    le_root, te_root = _winglet_side_chord(drawing, wing_z)
    le_tip, te_tip = _winglet_side_chord(drawing, tip_h)
    return (te_tip - le_tip) / (te_root - le_root)


def _prop_station(drawing: Drawing) -> float:
    nose = drawing.nose_station_side_ft()
    lo = min(drawing.bbox(i)[2] for i in (2780, 2786)) - nose
    hi = max(drawing.bbox(i)[3] for i in (2780, 2786)) - nose
    return (lo + hi) / 2.0


# --------------------------------------------------------------------------
# writers
# --------------------------------------------------------------------------


def status_mark(status: str) -> str:
    return {
        "match": "match",
        "off": "OFF",
        "no-model-value": "n/a",
    }.get(status, status)


def write_markdown(path: Path, payload: dict) -> None:
    lines: list[str] = []
    lines.append("# COZY Mark IV — dimension table")
    lines.append("")
    lines.append(
        "Every drawing value below was measured from `COZY3V.DXF` through "
        f"`measure_dxf.py`; no value was taken from memory or from the model. "
        "Model columns read the `P` dictionary of "
        "`Cozy_MKIV_OpenVSP_Baseline.py` without executing it."
    )
    lines.append("")
    lines.append(f"- source file: `{payload['source']['file']}`")
    lines.append(f"- source SHA-256: `{payload['source']['sha256']}`")
    lines.append(f"- digitised scale: `{payload['scale']['ft_per_unit']}` ft/unit")
    lines.append(f"- schema: `{payload['schema']}`")
    lines.append("")
    lines.append(
        "Status is `match` when |deviation| ≤ tolerance, `OFF` otherwise, "
        "`n/a` when the model has no corresponding parameter."
    )
    lines.append("")
    lines.append(
        "| # | quantity | drawing | unit | method | view / layers / entities | "
        "tol | model | deviation | status |"
    )
    lines.append("|---|---|---:|---|---|---|---:|---:|---:|---|")
    for i, row in enumerate(payload["rows"], 1):
        src = row["source"]
        where = (
            f"{src['view']} / L{','.join(src['layers'])} / "
            f"{_fmt_entities(src['entities'])}"
        )
        model = "—" if row["model_value"] is None else _fmt_num(row["model_value"])
        dev = "—" if row["deviation"] is None else _fmt_num(row["deviation"])
        lines.append(
            f"| {i} | {row['label']} | {_fmt_num(row['drawing_value'])} | "
            f"{row['unit']} | {row['method']} | {where} | {_fmt_num(row['tolerance'])} "
            f"| {model} | {dev} | {status_mark(row['status'])} |"
        )
    lines.append("")

    notes = [r for r in payload["rows"] if r.get("note")]
    if notes:
        lines.append("## Notes")
        lines.append("")
        for row in notes:
            lines.append(f"- **{row['id']}** — {row['note']}")
        lines.append("")

    checks = [
        (row["id"], row["cross_checks"])
        for row in payload["rows"]
        if row["cross_checks"]
    ]
    if checks:
        lines.append("## Cross checks")
        lines.append("")
        for row_id, entries in checks:
            for entry in entries:
                value = entry.get("value_ft", entry.get("value_ft2", entry.get("value_deg")))
                entities = _fmt_entities(entry["entities"])
                lines.append(
                    f"- **{row_id}** — {entry['label']}: "
                    f"`{_fmt_value(value)}` (entities {entities})"
                )
        lines.append("")

    limitations = payload.get("limitations") or []
    if limitations:
        lines.append("## Limitations carried from the digitisation")
        lines.append("")
        for item in limitations:
            lines.append(f"- {item}")

    while lines and not lines[-1].strip():
        lines.pop()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt_entities(entities: list[int]) -> str:
    if len(entities) <= 8:
        return ", ".join(str(i) for i in entities)
    head = ", ".join(str(i) for i in entities[:6])
    return f"{head}, … (+{len(entities) - 6})"


def _fmt_num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _fmt_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(_fmt_num(float(v)) for v in value)
    if isinstance(value, (int, float)):
        return _fmt_num(float(value))
    return str(value)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, default=OUT_JSON, help="path of dimensions.json"
    )
    parser.add_argument(
        "--markdown", type=Path, default=OUT_MD, help="path of DIMENSIONS.md"
    )
    parser.add_argument(
        "--loft", type=Path, default=OUT_LOFT, help="path of body_loft.json"
    )
    args = parser.parse_args(argv)

    record = json.loads(DIGITIZED.read_text(encoding="utf-8"))
    drawing = Drawing(record)
    model = load_model_parameters(BASELINE)

    length = drawing.bbox(457)[3] - drawing.nose_station_top_ft()
    stations = fuselage_profile_stations(drawing, length)
    sections = fuselage_profile(drawing, stations)
    min_z, max_z = silhouette_extrema(drawing)
    references = loft_reference_stations(drawing, sections, length)
    loft = {
        "schema": LOFT_SCHEMA,
        "source": {
            "file": DXF_NAME,
            "sha256": sha256_of(HERE / DXF_NAME),
            "digitised_record": DIGITIZED.name,
            "digitised_sha256": sha256_of(DIGITIZED),
        },
        "units": {"length": "ft"},
        "datums": {
            "station_origin": "plan-view nose outline 678",
            "height_origin": "side-view ground line 3217",
        },
        "outlines": {
            "side": BODY_SIDE_OUTLINE,
            "plan": BODY_PLAN_OUTLINE,
        },
        "length_ft": round(length, 6),
        "grid": {
            "cells": 31,
            "target_spacing_ft": round(length / 31.0, 6),
            "section_count": len(sections),
            "key_stations": (
                "widest, nose-top peak, turtledeck ramp foot and "
                "top, forward-body aft end, aft-body junction, "
                "tail face, tail"
            ),
        },
        "extrema": {
            "min_z_ft": round(min_z, 6),
            "max_z_ft": round(max_z, 6),
            "centre_z_ft": round((min_z + max_z) / 2.0, 6),
        },
        "sections": sections,
        "references": references,
        "method": (
            "Outer silhouette envelope of the side-view outlines "
            "1927/2692/2044 (height) and the plan-view outlines "
            "678/457 (width), sampled on a uniform station grid "
            "with the slope-change and outline-junction stations "
            "added, so the OpenVSP loft follows the drawn contour."
        ),
        "limitations": [
            "Section heights follow the side view; the front-view "
            "section 1148 is drawn taller than the side view at the "
            "same station",
            "The drawn lateral centre of the plan outlines wanders "
            "about 0.05 ft either side of the plan centreline; the "
            "loft is centred on the symmetry plane instead",
            "The aft-body forward face is near-vertical in the "
            "drawing; the loft ramps it between the two stations "
            "that bracket it",
        ],
    }
    args.loft.write_text(
        json.dumps(loft, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rows = build_rows(drawing, model, {
        "centre_z_ft": loft["extrema"]["centre_z_ft"],
        "min_z_ft": loft["extrema"]["min_z_ft"],
        "max_z_ft": loft["extrema"]["max_z_ft"],
        "references": loft["references"],
    })
    counts = {"match": 0, "off": 0, "no-model-value": 0}
    for row in rows:
        counts[row["status"]] += 1

    payload = {
        "schema": SCHEMA,
        "source": {
            "file": DXF_NAME,
            "sha256": sha256_of(HERE / DXF_NAME),
            "digitised_record": DIGITIZED.name,
            "digitised_sha256": sha256_of(DIGITIZED),
            "model_script": BASELINE.name,
        },
        "units": {"length": "ft", "area": "ft2", "angle": "deg"},
        "scale": record["scale"],
        "body_loft": args.loft.name,
        "datums": {
            "x_origin": "nose tip",
            "x_axis": "+x aft",
            "side_view_ground": f"LINE 3217 at x={drawing.side_ground_ft():.6f} ft",
            "front_view_ground": (
                f"lowest outline y={drawing.front_ground_ft():.6f} ft (wheel contact)"
            ),
            "plan_view_nose": (
                f"min outline y={drawing.nose_station_top_ft():.6f} ft"
            ),
            "side_view_nose": (
                f"min outline y={drawing.nose_station_side_ft():.6f} ft"
            ),
            "view_station_offset_ft": round(
                drawing.nose_station_top_ft() - drawing.nose_station_side_ft(), 6
            ),
        },
        "tolerances": TOLERANCE,
        "status_counts": counts,
        "rows": rows,
        "limitations": list(record.get("limitations") or []),
    }

    args.json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_markdown(args.markdown, payload)

    print(f"rows: {len(rows)}  {counts}")
    print(
        f"loft: {len(sections)} sections, centre z "
        f"{loft['extrema']['centre_z_ft']:.6f} ft"
    )
    print(f"wrote {args.json.name}, {args.markdown.name} and {args.loft.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
