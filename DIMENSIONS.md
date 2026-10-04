# COZY Mark IV — dimension table

Every drawing value below was measured from `COZY3V.DXF` through `measure_dxf.py`; no value was taken from memory or from the model. Model columns read the `P` dictionary of `Cozy_MKIV_OpenVSP_Baseline.py` without executing it.

- source file: `COZY3V.DXF`
- source SHA-256: `AF20FA74DFE3E98B675D98F86DBC1F713AA0B4A1386A1F7A632D1B5C5995D36E`
- digitised scale: `4.396697201227543` ft/unit
- schema: `cozy-dimensions/1`

Status is `match` when |deviation| ≤ tolerance, `OFF` otherwise, `n/a` when the model has no corresponding parameter.

| # | quantity | drawing | unit | method | view / layers / entities | tol | model | deviation | status |
|---|---|---:|---|---|---|---:|---:|---:|---|
| 1 | Overall length, nose to aftmost winglet tip | 16.9167 | ft | text-dimension | top / L5,8 / 3292, 3297, 3298, 3293, 3294, 3295, 3296 | 0.05 | 16.9167 | 0 | match |
| 2 | Overall span, winglet tip to winglet tip | 28.125 | ft | text-dimension | top / L5,8 / 3278, 3283, 3284, 3279, 3280, 3281, 3282 | 0.05 | 28.125 | 0 | match |
| 3 | Main wing planform area, wing panels plus strakes plus aileron strips | 88.5526 | ft2 | polyline-measured | top / L5 / 927, 1035, 974, 1082, 514, 596 | 0.5 | 88.5526 | 0 | match |
| 4 | Canard planform area including elevators | 12.9229 | ft2 | polyline-measured | top / L5 / 410, 1089, 1096 | 0.5 | 12.9229 | 0 | match |
| 5 | Canard span | 12.5636 | ft | polyline-measured | top / L5 / 410 | 0.05 | 12.5636 | 0 | match |
| 6 | Canard leading edge station from nose | 2.1395 | ft | polyline-measured | top / L5 / 410, 678 | 0.05 | 2.1395 | 0 | match |
| 7 | Canard leading edge sweep | 0 | deg | polyline-measured | top / L5 / 410 | 0.5 | 0 | 0 | match |
| 8 | Canard taper ratio | 1 | ratio | polyline-measured | top / L5 / 410, 1089, 1096 | 0.01 | 1 | 0 | match |
| 9 | Canard maximum chord | 1.1252 | ft | polyline-measured | top / L5 / 410, 1089, 1096 | 0.05 | — | — | n/a |
| 10 | Main wing leading edge sweep | 21.5838 | deg | polyline-measured | top / L5 / 927, 1035 | 0.5 | 21.5838 | 0 | match |
| 11 | Main wing taper ratio | 0.3743 | ratio | polyline-measured | top / L5 / 927, 1035 | 0.01 | 0.3743 | 0 | match |
| 12 | Main wing leading edge station at the centreline | 7.8839 | ft | polyline-measured | top / L5 / 927, 1035, 678 | 0.05 | 7.8839 | 0 | match |
| 13 | Main wing tip chord | 1.7171 | ft | polyline-measured | top / L5 / 927, 1035 | 0.05 | — | — | n/a |
| 14 | Fuselage length, nose to tail | 14.0194 | ft | polyline-measured | top / L5 / 678, 457 | 0.05 | 14.0194 | 0 | match |
| 15 | Fuselage maximum width | 3.4254 | ft | polyline-measured | top / L5 / 678 | 0.05 | 3.4254 | 0 | match |
| 16 | Spinner length | 1.351 | ft | polyline-measured | top / L5 / 478 | 0.05 | 1.351 | 0 | match |
| 17 | Spinner diameter | 0.9247 | ft | polyline-measured | top / L5 / 478 | 0.05 | 0.9247 | 0 | match |
| 18 | Winglet chordwise length in plan | 3.125 | ft | polyline-measured | top / L5 / 951, 1059 | 0.05 | — | — | n/a |
| 19 | Winglet root leading edge station | 13.7442 | ft | polyline-measured | top / L5 / 678, 951, 1059 | 0.05 | 13.7442 | 0 | match |
| 20 | Winglet aftmost station | 16.8692 | ft | polyline-measured | top / L5 / 678, 951, 1059 | 0.05 | 16.8692 | 0 | match |
| 21 | Winglet taper ratio | 0.2579 | ratio | polyline-measured | side / L5 / 2925, 2085, 3217, 1355 | 0.01 | 0.2579 | 0 | match |
| 22 | Winglet height above the wing | 4.5251 | ft | polyline-measured | front / L5 / 1355, 1458 | 0.05 | 4.5251 | 0 | match |
| 23 | Canard centre height above ground | 3.9409 | ft | polyline-measured | side / L5 / 2737, 3217 | 0.05 | 3.9409 | 0 | match |
| 24 | Main wing centre height above ground | 3.7695 | ft | polyline-measured | side / L5 / 2085, 3217 | 0.05 | 3.7695 | 0 | match |
| 25 | Propeller centre height above ground | 4.2268 | ft | polyline-measured | side / L5 / 2780, 2786, 3217 | 0.05 | 4.2268 | 0 | match |
| 26 | Propeller diameter | 5.6856 | ft | polyline-measured | side / L5 / 2780, 2786 | 0.05 | 5.6856 | 0 | match |
| 27 | Propeller disc station from nose | 14.1918 | ft | polyline-measured | side / L5 / 2780, 2786 | 0.05 | 14.1918 | 0 | match |
| 28 | Canopy top height above ground | 5.5322 | ft | polyline-measured | side / L5 / 2177, 3217 | 0.05 | — | — | n/a |
| 29 | Fuselage section centre height above ground | 3.3568 | ft | polyline-measured | side / L5 / 1927, 3217 | 0.05 | 3.3568 | 0 | match |
| 30 | Nose wheel diameter | 0.8349 | ft | polyline-measured | side / L5 / 2458, 3217 | 0.05 | 0.8349 | 0 | match |
| 31 | Main wheel diameter | 0.8652 | ft | polyline-measured | side / L5 / 2625, 3217 | 0.05 | 0.8652 | 0 | match |
| 32 | Main gear track, wheel centre to wheel centre | 5.8848 | ft | polyline-measured | front / L5 / 1109, 1788 | 0.05 | 5.8848 | 0 | match |

## Notes

- **overall_length_ft** — The model reports overall_length but no geometry is driven by it; the modelled overall length is fuselage length plus winglet overhang.
- **overall_span_ft** — The wing panel band of the front view stops 0.19 ft inboard of the dimensioned extremity; the winglet outline reaches it. The plan view wing panels reach the same extremity.
- **main_planform_area_ft2** — The drawn strakes stop at the fuselage sides, so the centre strip under the fuselage is not drawn. The model main wing is a single full-span trapezoid of equal total area; the shapes are not identical.
- **canard_span_ft** — Front view stops short of the plan view by the rounded canard tips.
- **canard_le_sweep_deg** — The model sets Sweep XSec_1 of the canard to 0.0 directly.
- **canard_taper** — The drawn tips are rounded, so the panel plus elevator shoelace area is smaller than a true rectangle; the model keeps the span and area drivers and the rectangular shape.
- **main_le_sweep_deg** — The baseline wing is built with Sweep XSec_1 = 0.
- **main_wing_taper** — The model wing is a single full-span trapezoid driven by span and area, so root and tip chord follow from the taper ratio.
- **main_root_le_from_nose_ft** — The drawn panels start at the strake junction, so the centreline leading edge is an extrapolation of the outer panel leading edge.
- **main_tip_chord_ft** — The panel is cut along the rounded wing tip, so the drawn tip edge is a diagonal longer than the local chord; the local chord is used here. The model derives root and tip chord from the SPAN/AREA/TAPER driver group, so no independent tip chord parameter exists.
- **winglet_le_from_nose_ft** — The winglet sits aft of the wing tip leading edge; the setback is 0.292141 ft.
- **winglet_aft_station_ft** — This is the aftmost point of the whole airframe and therefore sets the modelled overall length.
- **winglet_taper** — The side view winglet root chord is 0.05 ft longer than the main wing tip chord drawn in plan; the model root chord follows the wing.
- **winglet_height_ft** — Front and side views disagree on the winglet height by 0.216 ft; the front view is used because it shows the winglet full height without foreshortening.
- **canard_center_height_ft** — Front view sits higher than the side view; the side view carries the explicit ground line and is used as the height datum.
- **prop_diameter_ft** — The baseline hard-coded the propeller disk diameter at 5.80 ft.
- **prop_station_from_nose_ft** — Station origins are per view: each view is referenced to its own nose outline, so the raw sheet coordinates are not comparable. After that correction the views still disagree slightly - the spinner forward station differs by 0.018 ft and the canard leading edge by 0.061 ft between the plan and side views - so longitudinal stations carry about +/-0.05 ft of inter-view uncertainty. This row uses the side view because the propeller disc is only drawn there.
- **fuselage_center_height_ft** — The model fuselage cross sections are still scaled defaults, so only the datum can be matched, not the section shape.
- **nose_wheel_diameter_ft** — The model gear placeholders are wheel-envelope pods sized by this diameter and resting on the ground datum; they are not a landing-gear model.
- **main_wheel_diameter_ft** — The model gear placeholders are wheel-envelope pods sized by this diameter and resting on the ground datum; they are not a landing-gear model.
- **main_gear_track_ft** — The model main-gear placeholders are placed at plus/minus half of this track and rest on the ground datum; they are not a landing-gear model.

## Cross checks

- **overall_length_ft** — arrow span: `16.9167` (entities 3297, 3298)
- **overall_length_ft** — top outline nose to winglet aft tip: `16.8692` (entities 678, 951, 1059)
- **overall_span_ft** — top-view arrow span: `28.125` (entities 3283, 3284)
- **overall_span_ft** — front-view dimension 3285: `28.125` (entities 3285, 3290, 3291)
- **overall_span_ft** — front-view outline extent (winglets 1355/1458): `28.0485` (entities 1355, 1458)
- **overall_span_ft** — top-view outline extent (wing panels 927/1035): `28.1506` (entities 927, 1035)
- **overall_span_ft** — front-view wing panel band (1385/1488): `27.664` (entities 1385, 1488)
- **main_planform_area_ft2** — wing panels only: `51.6375` (entities 927, 1035)
- **main_planform_area_ft2** — aileron strips only: `3.8378` (entities 974, 1082)
- **main_planform_area_ft2** — strakes only: `33.0774` (entities 514, 596)
- **canard_planform_area_ft2** — canard panel only: `10.8211` (entities 410)
- **canard_span_ft** — front-view canard panels 1399/1344/1502: `12.3808` (entities 1399, 1344, 1502)
- **canard_le_from_nose_ft** — side-view canard 2737 station range: `2.0783, 3.2723` (entities 2737)
- **main_le_sweep_deg** — right panel 1035: `21.5838` (entities 1035)
- **main_wing_taper** — root chord: `4.5874` (entities 927, 1035)
- **main_wing_taper** — tip chord at the half-span: `1.7171` (entities 927, 1035)
- **fuselage_length_ft** — side view outline 1927 + 2044: `14.0612` (entities 1927, 2044)
- **fuselage_max_width_ft** — front-view fuselage section 1148: `3.4624` (entities 1148)
- **spinner_length_ft** — side view spinner 3032: `1.3115` (entities 3032)
- **spinner_diameter_ft** — side view spinner 3032 height: `0.8444` (entities 3032)
- **winglet_plan_length_ft** — side view winglet 2925: `3.2667` (entities 2925)
- **winglet_le_from_nose_ft** — main wing tip leading edge at the half-span: `13.4521` (entities 927, 1035)
- **winglet_le_from_nose_ft** — side view winglet leading edge at the wing plane: `14.0325` (entities 2925, 2085, 3217)
- **winglet_aft_station_ft** — dimensioned overall length: `16.9167` (entities 3292, 3297, 3298)
- **winglet_aft_station_ft** — side view winglet 2925 aft station: `17.0462` (entities 2925)
- **winglet_height_ft** — side view winglet 2925: `4.7408` (entities 2925)
- **winglet_height_ft** — front view height of winglet base: `3.5555` (entities 1355)
- **canard_center_height_ft** — front view canard 1399/1344/1502: `4.2298` (entities 1399, 1344, 1502)
- **wing_center_height_ft** — front view wing band 1385/1488: `3.8837` (entities 1385, 1488)
- **prop_center_height_ft** — side view spinner 3032 centre: `4.2069` (entities 3032)
- **prop_diameter_ft** — blade gap at hub (inner radii): `0.8558` (entities 2780, 2786)
- **prop_station_from_nose_ft** — side view spinner 3032 forward station: `14.0462` (entities 3032)
- **prop_station_from_nose_ft** — side view spinner 3032 aft station: `15.3578` (entities 3032)
- **prop_station_from_nose_ft** — top view spinner 478 forward station: `14.0645` (entities 478)
- **prop_station_from_nose_ft** — top view spinner 478 aft station: `15.4155` (entities 478)
- **canopy_top_height_ft** — front view canopy 1602: `5.7177` (entities 1602)
- **fuselage_center_height_ft** — front view fuselage section 1148: `3.4908` (entities 1148)
- **fuselage_center_height_ft** — rear fuselage 2044: `3.6541` (entities 2044)
- **nose_wheel_diameter_ft** — front view nose wheel 1254: `0.7599` (entities 1254)
- **main_wheel_diameter_ft** — front view main wheel 1788: `0.7609` (entities 1788)

## Limitations carried from the digitisation

- Only dimension texts are stated dimensions; all other values are measurements of drawing geometry multiplied by the solved scale.
- points_ft uses the drawing origin, not an aircraft datum.
- View labels come from fixed thresholds, verified by empty-band checks and a rendered preview; they are not from layer names.
- The aft part of the side view (entities 2780-3111: propeller, spinner, winglet) sits beyond the fuselage outline on the sheet. It was tested and belongs to the side view, not a separate detail view: its entity indices interleave with the rest of the side view, its outlines touch the rear-fuselage and wing outlines at zero distance, and its spinner measures 1.312 x 0.844 ft against 1.351 x 0.925 ft in the top view, i.e. the same 1:1 scale. It is therefore reported as view=side.
- Polylines are open/closed as stored (POLYLINE flag 0 for all 92); the file has no arcs, bulges or z coordinates.
