"""
Skill: ASAM OpenODD Generator & Validator
Synthesizes and validates machine-readable ASAM OpenODD 1.0 specifications
against formal JSON Schema and automotive regulatory constraints.
"""

import sys
import json
import yaml
import jsonschema
from pathlib import Path
from typing import Dict, Any

def build_and_validate_openodd(
    spec_data: Dict[str, Any],
    schema_path: Path,
    output_path: Path
) -> Dict[str, Any]:
    # 1. Validate against JSON schema
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
    lead_time = hysteresis.get("exit_warning_lead_time_s", 0.0)

    # UN R157 Rule: L3 highway pilot requires >= 10.0s transition demand lead time
    has_l3 = any("L3" in m.get("mode", "") for m in modes)
    if has_l3 and lead_time < 10.0:
        return {
            "status": "FAIL",
            "stage": "REGULATORY_GUARDRAIL",
            "error": f"UN R157 Violation: L3 operational mode requires exit_warning_lead_time_s >= 10.0s (found {lead_time}s)"
        }

    # Write output YAML
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec_data, f, sort_keys=False, default_flow_style=False)

    return {
        "status": "PASS",
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
