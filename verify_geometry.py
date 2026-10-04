"""Independent geometry verification for the saved Cozy MK IV model.

The .vsp3 file is opened read-only. Every quantity that dimensions.json holds
as a drawing value is re-measured from the model geometry and compared against
that drawing value using the row's own tolerance:

* rows with a ``model_parameter`` are scored -- any deviation beyond the row
  tolerance fails the run;
* rows without one are measured when the geometry exposes them and reported as
  a warning, because the design deliberately has no parameter for them;
* rows whose quantity the model does not contain at all are skipped.

Additional structural criteria, fixed up front:
1. Exactly 17 geometries, unique names.
2. Winglet root chord equals the main wing tip chord x-projection within 1e-6 ft.
3. Winglet roots sit on the wing tips laterally (correct side) and their root
   chord line lies in the wing plane within 1e-6 ft. The wing tip is washed out
   -6.5 deg, so its leading edge rides above that plane, and the drawing places
   the winglet root aft of the wing tip leading edge; both residuals are
   reported as INFO rather than scored.
4. Canard XSec_1 sweep is 0 degrees, main wing tip twist is -6.5 degrees.
5. Zero OpenVSP API errors.

Units: ft, deg. Read-only: the model file is never modified here.
"""

import json
import math
import sys
from pathlib import Path

import openvsp as vsp

HERE = Path(__file__).resolve().parent
MODEL = HERE / "Cozy_MKIV_Baseline.vsp3"
DIMENSIONS = HERE / "dimensions.json"
OUT_JSON = HERE / "Cozy_MKIV_Baseline.verify.json"
GEOM_TOL = 1e-6

FAILURES = []
WARNINGS = []


def box(gid):
    lo = vsp.GetGeomBBoxMin(gid)
    hi = vsp.GetGeomBBoxMax(gid)
    return (lo.x(), lo.y(), lo.z()), (hi.x(), hi.y(), hi.z())


def extent(b, axis):
    return b[1][axis] - b[0][axis]


def mid(b, axis):
    return (b[0][axis] + b[1][axis]) / 2.0


def point(gid, u, w):
    p = vsp.CompPnt01(gid, 0, u, w)
    return (p.x(), p.y(), p.z())


def chord_x(gid, u):
    le = point(gid, u, 0.5)
    te = point(gid, u, 0.0)
    return abs(te[0] - le[0])


def sweep_deg(gid):
    root = point(gid, 0.0, 0.5)
    tip = point(gid, 1.0, 0.5)
    return math.degrees(math.atan2(tip[0] - root[0], tip[1] - root[1]))


def structural(name, value, target, tol):
    ok = abs(value - target) <= tol
    print(f"{'PASS' if ok else 'FAIL'} {name}: {value!r} vs {target!r}")
    if not ok:
        FAILURES.append(name)
    return {"name": name, "actual": value, "expected": target,
            "abs_tol": tol, "passed": ok}


def main():
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(MODEL))
    manager = vsp.ErrorMgrSingleton.getInstance()
    structural("api_errors", manager.GetNumTotalErrors(), 0, 0)

    geoms = vsp.FindGeoms()
    structural("geometry_count", len(geoms), 17, 0)
    structural("unique_names", len({vsp.GetGeomName(g) for g in geoms}), len(geoms), 0)
    by_name = {vsp.GetGeomName(g): g for g in geoms}

    def named(fragment):
        hits = [g for n, g in by_name.items() if fragment in n]
        if len(hits) != 1:
            raise RuntimeError(f"expected exactly one geometry containing "
                               f"{fragment!r}, got {len(hits)}")
        return hits[0]

    main_wing = by_name["Main Wing"]
    canard = named("Canard")
    fuselage = named("Fuselage")
    spinner = named("Pusher propeller spinner")
    prop = named("Pusher propeller disk")
    winglet = named("Left main-wing tip winglet")
    nose_gear = named("Nose gear")
    left_gear = named("Left main gear")
    right_gear = named("Right main gear")

    whole = (
        tuple(min(b[0][i] for b in (box(g) for g in geoms)) for i in range(3)),
        tuple(max(b[1][i] for b in (box(g) for g in geoms)) for i in range(3)),
    )

    structural("canard_sweep_parm_deg", vsp.GetParmVal(canard, "Sweep", "XSec_1"), 0.0, 0)
    structural("main_tip_twist_deg", vsp.GetParmVal(main_wing, "Twist", "XSec_1"), -6.5, 0)

    tip_le = point(main_wing, 1.0, 0.5)
    tip_te = point(main_wing, 1.0, 0.0)
    tip_chord_x = abs(tip_te[0] - tip_le[0])
    wing_plane_z = point(main_wing, 0.0, 0.5)[2]
    structural("winglet_root_chord_x_equals_wing_tip_chord_x",
               abs(chord_x(winglet, 0.0) - tip_chord_x), 0.0, GEOM_TOL)

    winglet_root = point(winglet, 0.0, 0.5)

    # The winglet roots sit on the wing tips laterally, but the tip section is
    # washed out -6.5 deg, so its leading edge rides above the wing plane while
    # the (untilted) winglet root chord line stays in the wing plane. The plan
    # setback from the drawing is scored through winglet_le_from_nose_ft.
    for name, sign in (("Left main-wing tip winglet", -1.0),
                       ("Right main-wing tip winglet", 1.0)):
        root = point(by_name[name], 0.0, 0.5)
        structural(f"{name}: root_abs_y_equals_wing_tip_abs_y",
                   abs(abs(root[1]) - abs(tip_le[1])), 0.0, GEOM_TOL)
        structural(f"{name}: root_y_sign", math.copysign(1.0, root[1]), sign, 0)
        structural(f"{name}: root_z_equals_wing_plane_z",
                   abs(root[2] - wing_plane_z), 0.0, GEOM_TOL)

    info = {
        "wing_tip_twist_le_rise_ft": tip_le[2] - wing_plane_z,
        "winglet_root_setback_from_wing_tip_le_ft": winglet_root[0] - tip_le[0],
        "winglet_root_te_overhang_beyond_wing_tip_te_ft":
            point(winglet, 0.0, 0.0)[0] - tip_te[0],
    }
    for key, value in info.items():
        print(f"INFO {key}: {value:.6f}")

    measured = {
        "overall_length_ft": extent(whole, 0),
        "overall_span_ft": 2.0 * abs(tip_le[1]),
        "main_planform_area_ft2": vsp.GetParmVal(main_wing, "TotalArea", "WingGeom"),
        "canard_planform_area_ft2": vsp.GetParmVal(canard, "TotalArea", "WingGeom"),
        "canard_span_ft": 2.0 * abs(point(canard, 1.0, 0.5)[1]),
        "canard_le_from_nose_ft": point(canard, 0.0, 0.5)[0],
        "canard_le_sweep_deg": sweep_deg(canard),
        "canard_taper": chord_x(canard, 1.0) / chord_x(canard, 0.0),
        "canard_max_chord_ft": chord_x(canard, 0.0),
        "main_le_sweep_deg": sweep_deg(main_wing),
        "main_wing_taper": chord_x(main_wing, 1.0) / chord_x(main_wing, 0.0),
        "main_root_le_from_nose_ft": point(main_wing, 0.0, 0.5)[0],
        "main_tip_chord_ft": tip_chord_x,
        "fuselage_length_ft": extent(box(fuselage), 0),
        "fuselage_max_width_ft": max(extent(box(fuselage), 1), extent(box(fuselage), 2)),
        "spinner_length_ft": extent(box(spinner), 0),
        "spinner_diameter_ft": max(extent(box(spinner), 1), extent(box(spinner), 2)),
        "winglet_plan_length_ft": point(winglet, 1.0, 0.0)[0] - winglet_root[0],
        "winglet_le_from_nose_ft": winglet_root[0],
        "winglet_aft_station_ft": point(winglet, 1.0, 0.0)[0],
        "winglet_taper": chord_x(winglet, 1.0) / chord_x(winglet, 0.0),
        "winglet_height_ft": point(winglet, 1.0, 0.5)[2] - winglet_root[2],
        "canard_center_height_ft": point(canard, 0.0, 0.5)[2],
        "wing_center_height_ft": point(main_wing, 0.0, 0.5)[2],
        "prop_center_height_ft": mid(box(prop), 2),
        "prop_diameter_ft": 2.0 * max(abs(box(prop)[0][1]), abs(box(prop)[1][1])),
        "prop_station_from_nose_ft": mid(box(prop), 0),
        "fuselage_center_height_ft": mid(box(fuselage), 2),
        "nose_wheel_diameter_ft": extent(box(nose_gear), 2),
        "main_wheel_diameter_ft": extent(box(left_gear), 2),
        "main_gear_track_ft": mid(box(right_gear), 1) - mid(box(left_gear), 1),
    }

    table = json.loads(DIMENSIONS.read_text(encoding="utf-8"))
    results = []
    for row in table["rows"]:
        row_id = row["id"]
        if row_id not in measured:
            results.append({
                "id": row_id, "state": "not-measured",
                "drawing_value": row["drawing_value"],
            })
            continue
        actual = measured[row_id]
        deviation = actual - row["drawing_value"]
        tolerance = row["tolerance"]
        scored = row["model_parameter"] is not None
        passed = abs(deviation) <= tolerance
        state = "match" if passed else ("off" if scored else "warn")
        results.append({
            "id": row_id, "state": state, "scored": scored,
            "drawing_value": row["drawing_value"], "model_value": round(actual, 6),
            "deviation": round(deviation, 6), "tolerance": tolerance,
            "model_parameter": row["model_parameter"],
        })
        label = "PASS" if passed else ("FAIL" if scored else "WARN")
        print(f"{label} {row_id}: {actual:.6f} vs {row['drawing_value']:.6f} "
              f"(dev {deviation:+.6f}, tol {tolerance})")
        if not passed and scored:
            FAILURES.append(row_id)
        elif not passed:
            WARNINGS.append(row_id)

    OUT_JSON.write_text(
        json.dumps({
            "model": MODEL.name,
            "dimension_table": DIMENSIONS.name,
            "schema": table["schema"],
            "scored_rows": sum(1 for r in results if r.get("scored")),
            "failures": FAILURES,
            "warnings": WARNINGS,
            "info": {k: round(v, 6) for k, v in info.items()},
            "results": results,
        }, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print("RESULT", "PASS" if not FAILURES else f"FAIL {FAILURES}")
    if WARNINGS:
        print("WARNINGS (rows with no model parameter):", WARNINGS)
    print("Report:", OUT_JSON)
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
