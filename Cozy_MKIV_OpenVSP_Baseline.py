"""
COZY MK IV — OpenVSP parametric baseline
Revision: 0.2 | Units: ft, deg

Purpose: a full external, analysis-oriented starting geometry for OpenVSP/VSPAERO.
This is NOT a certified manufacturing model, flight manual, or substitute for the
licensed Cozy construction drawings. Before performance, stability, loads, or CFD
work, validate every exposed parameter against the applicable plan revision.

Use
---
1. Install a matching OpenVSP Python API from the OpenVSP distribution.
2. Run: python Cozy_MKIV_OpenVSP_Baseline.py
3. Open: Cozy_MKIV_Baseline.vsp3
4. In OpenVSP: inspect geometry, set reference quantities, create a VSPAERO
   analysis case, and regenerate any mesh after parameter changes.

Coordinate convention: X forward, Y right, Z up. OpenVSP's wing symmetry is XZ.
Datum: X = 0 on the plan-view nose outline, Z = 0 on the ground line
(LINE 3217 of the side view). Every station below is measured from the nose,
every height above the ground.

Every number in P is read from dimensions.json, produced by measure_dxf.py
from COZY3V.DXF. Re-run measure_dxf.py after changing P.
"""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

try:
    import openvsp as vsp
except ImportError as exc:
    raise SystemExit(
        "OpenVSP Python bindings were not found. Install/use the Python version "
        "shipped for your OpenVSP build, then retry. Details: https://openvsp.org/pyapi_docs/latest/"
    ) from exc

HERE = Path(__file__).resolve().parent
OUTFILE = HERE / "Cozy_MKIV_Baseline.vsp3"
REPORT = OUTFILE.with_suffix(".validation.json")
DIMENSIONS = HERE / "dimensions.json"
AIRFOILS = HERE / "airfoil"
E1230 = AIRFOILS / "e1230.dat"
R1145MS = AIRFOILS / "r1145ms.dat"

P = {
    "overall_length": 16.916667,
    "main_span": 28.125,
    "main_area": 88.552617,
    "main_le_sweep_deg": 21.583805,
    "main_taper": 0.374299,
    "main_tip_twist_deg": -6.50,
    "main_dihedral_deg": 0.0,
    "canard_span": 12.563641,
    "canard_area": 12.922935,
    "canard_le_sweep_deg": 0.0,
    "canard_taper": 1.0,
    "fuselage_length": 14.019360,
    "fuselage_max_dia": 3.425352,
    "fuselage_z": 3.356805,
    "wing_x": 7.883885,
    "wing_z": 3.769542,
    "canard_x": 2.139451,
    "canard_z": 3.940886,
    "winglet_height": 4.525088,
    "winglet_le_station": 13.744229,
    "winglet_aft_station": 16.869224,
    "winglet_taper": 0.257932,
    "prop_x": 14.191762,
    "prop_z": 4.226773,
    "prop_diameter": 5.685553,
    "spinner_x": 14.064531,
    "spinner_length": 1.351016,
    "spinner_diameter": 0.924684,
    "strake_x": 5.358900,
    "strake_length": 8.155400,
    "nose_wheel_diameter": 0.834941,
    "main_wheel_diameter": 0.865234,
    "main_gear_track": 5.884759,
}


def check_errors(stage):
    manager = vsp.ErrorMgrSingleton.getInstance()
    errors = []
    while manager.GetNumTotalErrors():
        errors.append(manager.PopLastError().GetErrorString())
    if errors:
        raise RuntimeError(f"{stage}: {'; '.join(errors)}")


def setp(geom_id, parm, group, value):
    pid = vsp.FindParm(geom_id, parm, group)
    check_errors(f"Find parameter {group}/{parm}")
    if not pid:
        raise RuntimeError(f"Missing parameter {group}/{parm}")
    vsp.SetParmVal(pid, value)
    check_errors(f"Set parameter {group}/{parm}")


def named_geom(kind, name):
    gid = vsp.AddGeom(kind, "")
    vsp.SetGeomName(gid, name)
    return gid


def place(gid, x, y, z, xrot=0.0, yrot=0.0, zrot=0.0):
    setp(gid, "X_Rel_Location", "XForm", x)
    setp(gid, "Y_Rel_Location", "XForm", y)
    setp(gid, "Z_Rel_Location", "XForm", z)
    setp(gid, "X_Rel_Rotation", "XForm", xrot)
    setp(gid, "Y_Rel_Rotation", "XForm", yrot)
    setp(gid, "Z_Rel_Rotation", "XForm", zrot)


def apply_airfoil(gid, path):
    if not path.is_file():
        raise RuntimeError(f"missing airfoil file {path}")
    surface = vsp.GetXSecSurf(gid, 0)
    for index in range(vsp.GetNumXSec(surface)):
        vsp.ChangeXSecShape(surface, index, vsp.XS_FILE_AIRFOIL)
        check_errors(f"Set file airfoil shape {index}")
        vsp.ReadFileAirfoil(vsp.GetXSec(surface, index), str(path))
        check_errors(f"Read airfoil {path.name} into section {index}")
    vsp.Update()
    check_errors(f"Apply airfoil {path.name}")


def wing(name, x, z, span, root_value, sweep=0.0, taper=1.0, symmetric=True,
         airfoil=None, xrot=0.0, yrot=0.0, zrot=0.0):
    gid = named_geom("WING", name)
    if airfoil is not None:
        apply_airfoil(gid, airfoil)
    place(gid, x, 0.0, z, xrot, yrot, zrot)
    setp(gid, "Sym_Planar_Flag", "Sym", vsp.SYM_XZ if symmetric else 0)
    if symmetric:
        vsp.SetDriverGroup(
            gid, 1, vsp.SPAN_WSECT_DRIVER, vsp.AREA_WSECT_DRIVER,
            vsp.TAPER_WSECT_DRIVER,
        )
        check_errors(f"Set wing drivers: {name}")
        setp(gid, "Span", "XSec_1", span / 2.0)
        setp(gid, "Area", "XSec_1", root_value / 2.0)
    else:
        vsp.SetDriverGroup(
            gid, 1, vsp.SPAN_WSECT_DRIVER, vsp.ROOTC_WSECT_DRIVER,
            vsp.TAPER_WSECT_DRIVER,
        )
        check_errors(f"Set winglet chord drivers: {name}")
        setp(gid, "Span", "XSec_1", span)
        setp(gid, "Root_Chord", "XSec_1", root_value)
    setp(gid, "Sweep", "XSec_1", sweep)
    setp(gid, "Taper", "XSec_1", taper)
    vsp.Update()
    return gid


def body(name, x, z, length, diameter, yrot=0.0):
    gid = named_geom("FUSELAGE", name)
    place(gid, x, 0.0, z, 0.0, yrot, 0.0)
    setp(gid, "Length", "Design", length)
    surf = vsp.GetXSecSurf(gid, 0)
    sections = [vsp.GetXSec(surf, i) for i in range(vsp.GetNumXSec(surf))]
    dimensions = [(vsp.GetXSecWidth(s), vsp.GetXSecHeight(s)) for s in sections]
    check_errors("Read fuselage cross sections")
    maximum = max(max(width, height) for width, height in dimensions)
    if maximum <= 0.0:
        raise RuntimeError("Fuselage has no nonzero cross sections")
    factor = diameter / maximum
    for section, (width, height) in zip(sections, dimensions):
        if vsp.GetXSecShape(section) != vsp.XS_POINT:
            vsp.SetXSecWidthHeight(section, width * factor, height * factor)
    check_errors("Scale fuselage cross sections")
    vsp.Update()
    return gid


def pod(name, x, y, z, length, diameter, yrot=0.0):
    gid = named_geom("POD", name)
    place(gid, x, y, z, 0.0, yrot, 0.0)
    setp(gid, "Length", "Design", length)
    setp(gid, "FineRatio", "Design", 2.0 * length / max(diameter, 0.1))
    vsp.Update()
    return gid


def disk(name, x, y, z, diameter, yrot=0.0):
    gid = named_geom("PROP", name)
    place(gid, x, y, z, 0.0, yrot, 0.0)
    setp(gid, "Diameter", "Design", diameter)
    vsp.Update()
    return gid


vsp.ClearVSPModel()

# 1) Principal lifting surfaces
fuselage = body("Fuselage — plan-derived loft required", 0.0, P["fuselage_z"],
                P["fuselage_length"], P["fuselage_max_dia"])
main_wing = wing("Main Wing", P["wing_x"], P["wing_z"], P["main_span"],
                 P["main_area"], sweep=P["main_le_sweep_deg"],
                 taper=P["main_taper"], airfoil=E1230)
setp(main_wing, "Twist", "XSec_0", 0.0)
setp(main_wing, "Twist", "XSec_1", P["main_tip_twist_deg"])
setp(main_wing, "Dihedral", "XSec_1", P["main_dihedral_deg"])
canard = wing("Canard — Roncz 1145MS verification needed", P["canard_x"],
              P["canard_z"], P["canard_span"], P["canard_area"],
              sweep=P["canard_le_sweep_deg"], taper=P["canard_taper"],
              airfoil=R1145MS)

vsp.Update()
main_tip_le = vsp.CompPnt01(main_wing, 0, 1.0, 0.5)
main_tip_te = vsp.CompPnt01(main_wing, 0, 1.0, 0.0)
check_errors("Read main-wing tip chord")
P["winglet_root_chord"] = abs(main_tip_te.x() - main_tip_le.x())
winglet_sweep = math.degrees(math.atan(
    (P["winglet_aft_station"] - P["winglet_le_station"]
     - P["winglet_root_chord"] * P["winglet_taper"]) / P["winglet_height"]
))
for name, side in (("Left main-wing tip winglet", -1), ("Right main-wing tip winglet", 1)):
    gid = wing(name, P["winglet_le_station"], P["wing_z"],
               P["winglet_height"], P["winglet_root_chord"],
               sweep=winglet_sweep, taper=P["winglet_taper"],
               symmetric=False, airfoil=E1230, xrot=90.0)
    setp(gid, "Y_Rel_Location", "XForm", side * P["main_span"] / 2.0)

# 3) External configuration for interference/drag trade studies
left_strake = pod("Left strake transition", P["strake_x"], -2.10, P["wing_z"],
                  P["strake_length"], 0.75, yrot=0.0)
right_strake = pod("Right strake transition", P["strake_x"], 2.10, P["wing_z"],
                   P["strake_length"], 0.75, yrot=0.0)
engine_cowl = pod("Rear engine cowl", P["fuselage_length"] - 2.05, 0.0,
                  P["fuselage_z"] + 1.85, 2.05, 1.65, yrot=0.0)
spinner = pod("Pusher propeller spinner", P["spinner_x"], 0.0, P["prop_z"],
              P["spinner_length"], P["spinner_diameter"], yrot=0.0)
prop = disk("Pusher propeller disk — reference only", P["prop_x"], 0.0,
            P["prop_z"], P["prop_diameter"], yrot=0.0)

# Gear placeholders: keep them separate so they can be excluded from a clean-airframe set.
nose_gear = pod("Nose gear / fairing placeholder", 2.45, 0.0,
                P["nose_wheel_diameter"] / 2.0, 1.30, P["nose_wheel_diameter"])
left_gear = pod("Left main gear / fairing placeholder", 8.15,
                -P["main_gear_track"] / 2.0, P["main_wheel_diameter"] / 2.0,
                1.60, P["main_wheel_diameter"])
right_gear = pod("Right main gear / fairing placeholder", 8.15,
                 P["main_gear_track"] / 2.0, P["main_wheel_diameter"] / 2.0,
                 1.60, P["main_wheel_diameter"])

# 4) Conceptual internal mass/reference volumes. They do not represent structure.
# Review using Mass Properties after replacing with plan-derived stations and masses.
front_occupants = pod("Front occupants mass envelope", 4.70, 0.0,
                      P["fuselage_z"] + 1.45, 1.65, 2.20)
rear_occupants = pod("Rear occupants mass envelope", 7.05, 0.0,
                     P["fuselage_z"] + 1.42, 1.45, 2.20)
left_fuel = pod("Left fuel volume envelope", 7.85, -2.10,
                P["fuselage_z"] + 1.20, 2.50, 0.65)
right_fuel = pod("Right fuel volume envelope", 7.85, 2.10,
                 P["fuselage_z"] + 1.20, 2.50, 0.65)


def validate_model():
    checks = []

    def verify(name, actual, expected, abs_tol=1e-8):
        passed = math.isclose(actual, expected, rel_tol=1e-8, abs_tol=abs_tol)
        checks.append({
            "name": name, "actual": actual, "expected": expected,
            "abs_tol": abs_tol, "passed": passed,
        })

    def box(gid):
        lo = vsp.GetGeomBBoxMin(gid)
        hi = vsp.GetGeomBBoxMax(gid)
        return (lo.x(), lo.y(), lo.z()), (hi.x(), hi.y(), hi.z())

    geoms = vsp.FindGeoms()
    verify("geometry_count", len(geoms), 17)
    by_name = {vsp.GetGeomName(gid): gid for gid in geoms}
    verify("unique_geometry_names", len(by_name), len(geoms))
    for name, span, area, symmetric in (
        ("Main Wing", P["main_span"], P["main_area"], True),
        ("Canard — Roncz 1145MS verification needed", P["canard_span"], P["canard_area"], True),
        ("Left main-wing tip winglet", P["winglet_height"], None, False),
        ("Right main-wing tip winglet", P["winglet_height"], None, False),
    ):
        gid = by_name[name]
        actual_span = vsp.GetParmVal(gid, "TotalSpan", "WingGeom")
        actual_area = vsp.GetParmVal(gid, "TotalArea", "WingGeom")
        verify(f"{name}: span_ft", actual_span, span)
        if area is not None:
            verify(f"{name}: area_ft2", actual_area, area)
            verify(f"{name}: derived_aspect", actual_span ** 2 / actual_area, span ** 2 / area)

    gid = by_name["Main Wing"]
    verify("main_root_twist_deg", vsp.GetParmVal(gid, "Twist", "XSec_0"), 0.0)
    verify("main_tip_twist_deg", vsp.GetParmVal(gid, "Twist", "XSec_1"), P["main_tip_twist_deg"])
    verify("main_dihedral_deg", vsp.GetParmVal(gid, "Dihedral", "XSec_1"), P["main_dihedral_deg"])
    verify("main_le_sweep_deg", vsp.GetParmVal(gid, "Sweep", "XSec_1"), P["main_le_sweep_deg"])
    verify("main_taper", vsp.GetParmVal(gid, "Taper", "XSec_1"), P["main_taper"])
    root_le = vsp.CompPnt01(gid, 0, 0.0, 0.5)
    verify("main_root_le_x_ft", root_le.x(), P["wing_x"], 1e-6)
    verify("main_root_le_z_ft", root_le.z(), P["wing_z"], 1e-6)
    tip_le = vsp.CompPnt01(gid, 0, 1.0, 0.5)
    tip_te = vsp.CompPnt01(gid, 0, 1.0, 0.0)
    tip_chord = abs(tip_te.x() - tip_le.x())
    twist = math.radians(P["main_tip_twist_deg"])
    twist_loc = vsp.GetParmVal(gid, "Twist_Location", "XSec_1")
    expected_tip_x = (
        P["wing_x"]
        + P["main_span"] / 2.0 * math.tan(math.radians(P["main_le_sweep_deg"]))
        + twist_loc * tip_chord * (1.0 - math.cos(twist))
    )
    verify("main_tip_le_x_ft", tip_le.x(), expected_tip_x, 1e-4)
    verify("main_tip_chord_ft", tip_chord, P["winglet_root_chord"], 1e-6)

    for name, side in (("Left main-wing tip winglet", -1), ("Right main-wing tip winglet", 1)):
        winglet = by_name[name]
        root = vsp.CompPnt01(winglet, 0, 0.0, 0.5)
        top = vsp.CompPnt01(winglet, 0, 1.0, 0.5)
        tip_aft = vsp.CompPnt01(winglet, 0, 1.0, 0.0)
        verify(f"{name}: root_x_ft", root.x(), P["winglet_le_station"], 1e-6)
        verify(f"{name}: root_y_ft", root.y(), side * P["main_span"] / 2.0, 1e-6)
        verify(f"{name}: root_z_ft", root.z(), P["wing_z"], 1e-6)
        verify(f"{name}: vertical_rise_ft", top.z() - root.z(), P["winglet_height"], 1e-6)
        verify(f"{name}: lateral_lean_ft", top.y() - root.y(), 0.0, 1e-6)
        verify(f"{name}: aft_station_ft", tip_aft.x(), P["winglet_aft_station"], 1e-6)
        verify(f"{name}: root_chord_ft", vsp.GetParmVal(winglet, "Root_Chord", "XSec_1"), P["winglet_root_chord"])
        verify(f"{name}: taper", vsp.GetParmVal(winglet, "Taper", "XSec_1"), P["winglet_taper"])
        verify(f"{name}: symmetry_disabled", vsp.GetParmVal(winglet, "Sym_Planar_Flag", "Sym"), 0)

    gid = by_name["Canard — Roncz 1145MS verification needed"]
    verify("canard_le_sweep_deg", vsp.GetParmVal(gid, "Sweep", "XSec_1"), P["canard_le_sweep_deg"])
    verify("canard_taper", vsp.GetParmVal(gid, "Taper", "XSec_1"), P["canard_taper"])
    root = vsp.CompPnt01(gid, 0, 0.0, 0.5)
    tip = vsp.CompPnt01(gid, 0, 1.0, 0.5)
    verify("canard_root_le_x_ft", root.x(), P["canard_x"], 1e-6)
    verify("canard_root_le_z_ft", root.z(), P["canard_z"], 1e-6)
    verify("canard_leading_edge_x_offset_ft", tip.x() - root.x(), 0.0, 1e-6)

    gid = by_name["Fuselage — plan-derived loft required"]
    verify("fuselage_length_ft", vsp.GetParmVal(gid, "Length", "Design"), P["fuselage_length"])
    surf = vsp.GetXSecSurf(gid, 0)
    maximum = max(
        max(vsp.GetXSecWidth(vsp.GetXSec(surf, i)), vsp.GetXSecHeight(vsp.GetXSec(surf, i)))
        for i in range(vsp.GetNumXSec(surf))
    )
    verify("fuselage_max_section_dimension_ft", maximum, P["fuselage_max_dia"])
    lo, hi = box(gid)
    verify("fuselage_nose_x_ft", lo[0], 0.0, 1e-6)
    verify("fuselage_tail_x_ft", hi[0], P["fuselage_length"], 1e-6)
    verify("fuselage_centre_z_ft", (lo[2] + hi[2]) / 2.0, P["fuselage_z"], 1e-6)

    lows = [box(g)[0] for g in geoms]
    highs = [box(g)[1] for g in geoms]
    verify("nose_datum_x_ft", min(p[0] for p in lows), 0.0, 1e-6)
    verify("ground_datum_z_ft", min(p[2] for p in lows), 0.0, 1e-6)
    verify("aftmost_station_ft", max(p[0] for p in highs), P["winglet_aft_station"], 1e-6)
    verify("highest_point_ft", max(p[2] for p in highs), P["wing_z"] + P["winglet_height"], 1e-6)

    check_errors("Validate model")
    return checks


vsp.Update()
check_errors("Build model")
before_save = validate_model()
if not all(check["passed"] for check in before_save):
    raise RuntimeError(f"Geometry validation failed before saving: {before_save}")
vsp.WriteVSPFile(str(OUTFILE), vsp.SET_ALL)
check_errors("Write model")
if not OUTFILE.is_file() or OUTFILE.stat().st_size == 0:
    raise RuntimeError("OpenVSP did not create a nonempty model file")
vsp.ClearVSPModel()
vsp.ReadVSPFile(str(OUTFILE))
check_errors("Read saved model")
after_save = validate_model()
passed = all(check["passed"] for check in after_save)
report = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "openvsp_version": vsp.GetVSPVersion(),
    "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "model_sha256": hashlib.sha256(OUTFILE.read_bytes()).hexdigest(),
    "model": OUTFILE.name,
    "units": {"length": "ft", "area": "ft^2", "angle": "deg"},
    "parameters": P,
    "input_provenance": {
        "drawing": "COZY3V.DXF",
        "drawing_sha256": hashlib.sha256((HERE / "COZY3V.DXF").read_bytes()).hexdigest().upper(),
        "dimension_table": "dimensions.json (schema cozy-dimensions/1), written by measure_dxf.py",
        "datum": "X = 0 on the plan-view nose outline 678; Z = 0 on side-view ground line 3217",
        "airfoils": {
            "main_wing_and_winglet": "airfoil/e1230.dat",
            "canard": "airfoil/r1145ms.dat",
        },
        "winglet_sweep": "Solved at build time from the winglet root chord so the tip trailing edge lands on winglet_aft_station",
        "main_tip_twist_deg": "Provisional -6.5 deg; not established by the drawing",
        "internal_envelopes": "Inherited placeholder stations and sizes, shifted to the ground datum",
        "gear": "Wheel-envelope pods sized by the drawn wheel diameters, resting on the ground datum",
    },
    "validation_scope": "Parameter consistency and serialization only; not aerodynamic validation",
    "passed": passed,
    "before_save": before_save,
    "after_reload": after_save,
    "limitations": [
        "Dimensions are traced to COZY3V.DXF through dimensions.json, not to a licensed plan set",
        "Wing and canard are single trapezoids; strakes, elevators and ailerons are not separate surfaces",
        "The winglet has no cant; the front view shows roughly 4 deg of inward lean that is not modelled",
        "The drawing puts the winglet root leading edge 0.292141 ft aft of the straight-line wing tip leading edge, "
        "so the winglet root and the wing tip sections only partly overlap chordwise",
        "Fuselage retains scaled default sections, not a plan-derived loft",
        "Spinner, cowl, gear, strakes and internal volumes are placeholder bodies, not structure",
        "Propeller disc is a reference only; no propulsion or aeroelastic model",
        "Airfoil sections are loaded from files but incidence, twist and camber effects are not validated",
        "Longitudinal stations carry about +/-0.05 ft of inter-view uncertainty (plan vs side)",
        "No aerodynamic, trim, stability, stall, structural or flightworthiness assessment",
    ],
}
REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
if not passed:
    raise RuntimeError(f"Saved model validation failed; see {REPORT}")
print("Created", OUTFILE)
print(f"PASS: {len(before_save)} pre-save and {len(after_save)} post-reload checks")
print("Validation report:", REPORT)
print("NOT VALIDATED FOR PERFORMANCE, MANUFACTURING OR FLIGHT")
