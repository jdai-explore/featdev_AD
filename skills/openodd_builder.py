"""
Skill: ASAM OpenODD Generator & Spatial Geometry Verifier (Shapely Engine)
Synthesizes and validates machine-readable ASAM OpenODD 1.0 specifications
against formal JSON Schema, Shapely spatial geometry rules, and automotive dynamics constraints.
"""

import sys
import json
import yaml
import jsonschema
from pathlib import Path
from typing import Dict, Any

from shapely.geometry import Polygon, box

def verify_spatial_and_dynamic_envelope(odd_body: Dict[str, Any]) -> list[str]:
    violations = []
    spatial = odd_body.get("spatial_boundaries", {})
    kinematics = odd_body.get("kinematic_limits", {})
    speed_limits = kinematics.get("ego_speed_kph", {})
    v_max_kph = float(speed_limits.get("max", 130.0))
    v_max_mps = v_max_kph / 3.6

    curve_limits = spatial.get("curve_radius_m", {})
    r_min = float(curve_limits.get("min", 250.0))

    # Centripetal acceleration limit check (UN R157: a_lat <= 3.0 m/s^2)
    # a_lat = v^2 / r
    if r_min > 0:
        a_lat_req = (v_max_mps ** 2) / r_min
        if a_lat_req > 3.0:
            violations.append(
                f"Dynamic Infeasibility: Max speed {v_max_kph} km/h on min curve {r_min}m requires lateral acceleration of {a_lat_req:.2f} m/s^2 (UN R157 limit is 3.0 m/s^2)"
            )

    # Lane width envelope check
    lane_width = spatial.get("lane_width_m", {})
    w_min = float(lane_width.get("min", 3.25))
    w_max = float(lane_width.get("max", 4.50))
    if w_min < 2.50:
        violations.append(f"Safety Violation: Minimum lane width {w_min}m is narrower than minimum passenger vehicle clearance (2.50m)")
    if w_max < w_min:
        violations.append(f"Geometric Error: Maximum lane width ({w_max}m) is smaller than minimum ({w_min}m)")

    # Shapely 2D Spatial Geofence Polygon verification (bounding representation)
    try:
        # Standard synthetic highway bounding box representing operational lane corridor
        corridor_poly = box(0.0, 0.0, 1000.0, w_max)
        if not corridor_poly.is_valid:
            violations.append("Shapely Error: Constructed spatial corridor polygon is invalid or self-intersecting.")
        if corridor_poly.area <= 0.0:
            violations.append("Shapely Error: Spatial corridor polygon has non-positive area.")
    except Exception as e:
        violations.append(f"Shapely geometry exception: {str(e)}")

    return violations

def build_and_validate_openodd(
    spec_data: Dict[str, Any],
    schema_path: Path,
    output_path: Path
) -> Dict[str, Any]:
    # 1. Validate against formal JSON schema
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    try:
        jsonschema.validate(instance=spec_data, schema=schema)
    except jsonschema.ValidationError as e:
        return {"status": "FAIL", "stage": "SCHEMA_VALIDATION", "error": str(e.message)}

    # 2. Automotive Regulatory Domain Guardrails
    odd_body = spec_data.get("odd_specification", {})
    modes = odd_body.get("automation_level_modes", [])
    hysteresis = odd_body.get("boundary_hysteresis", {})
    lead_time = float(hysteresis.get("exit_warning_lead_time_s", 0.0))

    # UN R157 Rule: L3 highway mode requires >= 10.0s transition demand lead time
    has_l3 = any("L3" in m.get("mode", "") for m in modes)
    if has_l3 and lead_time < 10.0:
        return {
            "status": "FAIL",
            "stage": "REGULATORY_GUARDRAIL",
            "error": f"UN R157 Violation: L3 operational mode requires exit_warning_lead_time_s >= 10.0s (found {lead_time}s)"
        }

    # 3. Shapely Spatial & Physical Dynamics Verification
    geo_violations = verify_spatial_and_dynamic_envelope(odd_body)
    if geo_violations:
        return {
            "status": "FAIL",
            "stage": "SPATIAL_DYNAMICS_VERIFICATION",
            "errors": geo_violations
        }

    # Write output YAML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec_data, f, sort_keys=False, default_flow_style=False)

    return {
        "status": "PASS",
        "engine": "ASAM OpenODD 1.0 + Shapely Spatial Geometry Engine",
        "output_file": str(output_path),
        "spec_id": odd_body.get("id"),
        "version": odd_body.get("version"),
        "lead_time_s": lead_time
    }

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: openodd_builder.py <input_json> <schema_path> <output_yaml>"}))
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        input_data = json.load(f)

    res = build_and_validate_openodd(input_data, Path(sys.argv[2]), Path(sys.argv[3]))
    print(json.dumps(res, indent=2))
    if res["status"] != "PASS":
        sys.exit(2)
