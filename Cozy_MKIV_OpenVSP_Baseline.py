"""
COZY MK IV — OpenVSP parametric baseline
Revision: 0.1 | Units: ft, deg

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

OUTFILE = Path(__file__).resolve().with_name("Cozy_MKIV_Baseline.vsp3")
REPORT = OUTFILE.with_suffix(".validation.json")
P = {
    "overall_length": 16.90,
    "main_span": 28.10,
    "main_area": 88.30,
    "canard_span": 11.50,
    "canard_area": 21.00,
    "fuselage_length": 16.90,
    "fuselage_max_dia": 3.50,
    "wing_x": 8.05,
    "wing_z": 1.45,
    "canard_x": 3.15,
    "canard_z": 1.95,
    "winglet_x": 13.20,
    "winglet_z": 1.75,
    "prop_x": 15.60,
    "prop_z": 2.10,
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


def wing(name, x, z, span, area, xrot=0.0, yrot=0.0, zrot=0.0):
    gid = named_geom("WING", name)
    place(gid, x, 0.0, z, xrot, yrot, zrot)
    setp(gid, "Sym_Planar_Flag", "Sym", vsp.SYM_XZ)
    vsp.SetDriverGroup(
        gid, 1, vsp.SPAN_WSECT_DRIVER, vsp.AREA_WSECT_DRIVER,
        vsp.TAPER_WSECT_DRIVER,
    )
    check_errors(f"Set wing drivers: {name}")
    setp(gid, "Span", "XSec_1", span / 2.0)
    setp(gid, "Area", "XSec_1", area / 2.0)
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
    setp(gid, "FineRatio", "Design", max(1.1, length / max(diameter, 0.1)))
    vsp.Update()
    return gid


def disk(name, x, y, z, diameter, yrot=90.0):
    gid = named_geom("PROP", name)
    place(gid, x, y, z, 0.0, yrot, 0.0)
    setp(gid, "Diameter", "Design", diameter)
    vsp.Update()
    return gid


vsp.ClearVSPModel()

# 1) Principal lifting surfaces
fuselage = body("Fuselage — plan-derived loft required", 0.0, 0.0,
                P["fuselage_length"], P["fuselage_max_dia"])
main_wing = wing("Main Wing", P["wing_x"], P["wing_z"], P["main_span"],
                 P["main_area"], xrot=0.0, yrot=0.0, zrot=0.0)
canard = wing("Canard — Roncz 1145MS verification needed", P["canard_x"],
              P["canard_z"], P["canard_span"], P["canard_area"],
              xrot=0.0, yrot=0.0, zrot=0.0)

# 2) Vertical endplates / winglets. These are separate, symmetric vertical wings.
winglets = wing("Main-wing tip winglets", P["winglet_x"], P["winglet_z"],
                3.00, 8.00, xrot=0.0, yrot=0.0, zrot=90.0)

# 3) External configuration for interference/drag trade studies
# Strakes are modeled as low-profile transition volumes. Replace with plan stations.
left_strake = pod("Left strake transition", 6.70, -2.10, 1.12, 4.10, 0.75, yrot=0.0)
right_strake = pod("Right strake transition", 6.70, 2.10, 1.12, 4.10, 0.75, yrot=0.0)
engine_cowl = pod("Rear engine cowl", 13.25, 0.0, 1.85, 2.05, 1.65, yrot=0.0)
spinner = pod("Pusher propeller spinner", 15.00, 0.0, P["prop_z"], 0.70, 0.55, yrot=0.0)
prop = disk("Pusher propeller disk — reference only", P["prop_x"], 0.0,
            P["prop_z"], 5.80, yrot=90.0)

# Gear placeholders: keep them separate so they can be excluded from a clean-airframe set.
nose_gear = pod("Nose gear / fairing placeholder", 2.45, 0.0, -0.85, 1.30, 0.25)
left_gear = pod("Left main gear / fairing placeholder", 8.15, -2.45, -0.90, 1.60, 0.30)
right_gear = pod("Right main gear / fairing placeholder", 8.15, 2.45, -0.90, 1.60, 0.30)

# 4) Conceptual internal mass/reference volumes. They do not represent structure.
# Review using Mass Properties after replacing with plan-derived stations and masses.
front_occupants = pod("Front occupants mass envelope", 4.70, 0.0, 1.45, 1.65, 2.20)
rear_occupants = pod("Rear occupants mass envelope", 7.05, 0.0, 1.42, 1.45, 2.20)
left_fuel = pod("Left fuel volume envelope", 7.85, -2.10, 1.20, 2.50, 0.65)
right_fuel = pod("Right fuel volume envelope", 7.85, 2.10, 1.20, 2.50, 0.65)

def validate_model():
    checks = []

    def verify(name, actual, expected):
        passed = math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-8)
        checks.append({
            "name": name, "actual": actual, "expected": expected, "passed": passed,
        })

    geoms = vsp.FindGeoms()
    verify("geometry_count", len(geoms), 16)
    by_name = {vsp.GetGeomName(gid): gid for gid in geoms}
    verify("unique_geometry_names", len(by_name), len(geoms))
    for name, span, area in (
        ("Main Wing", P["main_span"], P["main_area"]),
        ("Canard — Roncz 1145MS verification needed", P["canard_span"], P["canard_area"]),
        ("Main-wing tip winglets", 3.0, 8.0),
    ):
        gid = by_name[name]
        actual_span = vsp.GetParmVal(gid, "TotalSpan", "WingGeom")
        actual_area = vsp.GetParmVal(gid, "TotalArea", "WingGeom")
        verify(f"{name}: span_ft", actual_span, span)
        verify(f"{name}: area_ft2", actual_area, area)
        verify(f"{name}: derived_aspect", actual_span ** 2 / actual_area, span ** 2 / area)
    gid = by_name["Fuselage — plan-derived loft required"]
    verify("fuselage_length_ft", vsp.GetParmVal(gid, "Length", "Design"), P["fuselage_length"])
    surf = vsp.GetXSecSurf(gid, 0)
    maximum = max(
        max(vsp.GetXSecWidth(vsp.GetXSec(surf, i)), vsp.GetXSecHeight(vsp.GetXSec(surf, i)))
        for i in range(vsp.GetNumXSec(surf))
    )
    verify("fuselage_max_section_dimension_ft", maximum, P["fuselage_max_dia"])
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
    "validation_scope": "Parameter consistency and serialization only; not aerodynamic validation",
    "passed": passed,
    "before_save": before_save,
    "after_reload": after_save,
    "limitations": [
        "Dimensions have not been traced to drawings or manual pages",
        "Winglets retain the original placeholder location and rotation; not validated as vertical tip surfaces",
        "Airfoils, sweep, taper, twist and incidence are not plan-validated",
        "Fuselage retains scaled default sections, not a plan-derived loft",
        "Propeller mode and orientation are unverified; no propulsion analysis",
        "Internal envelopes are not calibrated masses and remain in SET_ALL",
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
