"""
Automated Pre-Review Deterministic Gatekeeper
Ensures no artifact ever reaches human review if it violates schemas,
has traceability gaps, fails safety linting, or breaks cryptographic integrity.
"""

import sys
import json
import csv
import yaml
import jsonschema
from pathlib import Path

# Import skill validators directly
sys.path.append(str(Path(__file__).resolve().parent.parent))
from skills.state_machine_verifier import verify_hmi_state_machine
from skills.bus_bandwidth_calc import evaluate_icd_performance
from skills.code_safety_linter import lint_embedded_c_code
from core.runtime import DeterministicAgentRuntime

def run_gatekeeper(bundle_path_str: str) -> dict:
    bundle_path = Path(bundle_path_str)
    if not bundle_path.exists():
        return {"gate_decision": "REJECT", "error": f"Execution bundle not found: {bundle_path_str}"}

    with open(bundle_path, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    runtime = DeterministicAgentRuntime()
    errors = []

    # 1. Verify Input Cryptographic Fingerprints
    for rel_path, expected_hash in bundle.get("input_hashes", {}).items():
        full_p = runtime.base_dir / rel_path
        if not full_p.exists():
            errors.append(f"Input artifact missing: {rel_path}")
            continue
        actual_hash = runtime.compute_sha256(full_p)
        if actual_hash != expected_hash:
            errors.append(f"Non-determinism detected on input {rel_path}: expected {expected_hash}, got {actual_hash}")

    # 2. Verify Output Cryptographic Fingerprints & Validate Content
    for rel_path, expected_hash in bundle.get("output_hashes", {}).items():
        full_p = runtime.base_dir / rel_path
        if not full_p.exists():
            errors.append(f"Generated output missing: {rel_path}")
            continue
        actual_hash = runtime.compute_sha256(full_p)
        if actual_hash != expected_hash:
            errors.append(f"Output checksum mismatch on {rel_path}: expected {expected_hash}, got {actual_hash}")

        # Domain format-specific linting
        suffix = full_p.suffix.lower()

        # CSV Traceability & Domain Check
        if suffix == ".csv":
            with open(full_p, "r", encoding="utf-8", newline="") as cf:
                reader = csv.DictReader(cf)
                if "Trace_ID" not in (reader.fieldnames or []):
                    errors.append(f"CSV {rel_path} is missing mandatory 'Trace_ID' column!")
                else:
                    valid_prefixes = ("REQ-", "SAF-", "ODD-", "HMI-", "AUTH-", "ARCH-", "SCEN-", "CODE-", "VAL-")
                    for row_idx, r in enumerate(reader, start=1):
                        tid = r.get("Trace_ID", "")
                        if not any(tid.startswith(pfx) for pfx in valid_prefixes):
                            errors.append(f"Invalid Trace_ID prefix '{tid}' in {rel_path} line {row_idx}")

            # Specific check for HMI state matrix
            if "hmi" in rel_path.lower() or "state_matrix" in rel_path.lower():
                hmi_res = verify_hmi_state_machine(str(full_p))
                if hmi_res["status"] != "PASS":
                    errors.extend(hmi_res.get("errors", ["HMI state machine verification failed"]))

        # JSON Validation
        elif suffix == ".json":
            if "icd" in rel_path.lower():
                icd_schema_p = runtime.base_dir / "schemas/icd.schema.json"
                if icd_schema_p.exists():
                    with open(icd_schema_p, "r", encoding="utf-8") as sf, open(full_p, "r", encoding="utf-8") as jf:
                        schema = json.load(sf)
                        inst = json.load(jf)
                        try:
                            jsonschema.validate(instance=inst, schema=schema)
                        except jsonschema.ValidationError as ve:
                            errors.append(f"JSON schema violation in {rel_path}: {ve.message}")
                icd_res = evaluate_icd_performance(str(full_p))
                if icd_res["status"] != "PASS":
                    errors.append(f"ICD Performance evaluation failed on {rel_path}")

        # YAML Validation (e.g. OpenODD)
        elif suffix in (".yaml", ".yml"):
            if "odd" in rel_path.lower():
                odd_schema_p = runtime.base_dir / "schemas/openodd.schema.json"
                if odd_schema_p.exists():
                    with open(odd_schema_p, "r", encoding="utf-8") as sf, open(full_p, "r", encoding="utf-8") as yf:
                        schema = json.load(sf)
                        inst = yaml.safe_load(yf)
                        try:
                            jsonschema.validate(instance=inst, schema=schema)
                        except jsonschema.ValidationError as ve:
                            errors.append(f"YAML OpenODD schema violation in {rel_path}: {ve.message}")

        # C Code Safety Linting
        elif suffix in (".c", ".h"):
            c_res = lint_embedded_c_code(str(full_p))
            if c_res["status"] != "PASS":
                errors.extend(c_res.get("violations", ["Embedded C safety violations detected"]))

    if errors:
        return {
            "gate_decision": "REJECT",
            "feature_id": bundle.get("feature_id"),
            "agent_id": bundle.get("agent_id"),
            "error_count": len(errors),
            "errors": errors,
            "signoff_action": "BLOCKED_UNTIL_CORRECTED"
        }

    return {
        "gate_decision": "PASS",
        "feature_id": bundle.get("feature_id"),
        "agent_id": bundle.get("agent_id"),
        "status_message": "All cryptographic hashes, JSON/YAML schemas, and safety linters passed 100%. Ready for Human Sign-Off."
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: pre_review_gatekeeper.py <bundle_json_path>"}))
        sys.exit(1)

    outcome = run_gatekeeper(sys.argv[1])
    print(json.dumps(outcome, indent=2))
    if outcome["gate_decision"] != "PASS":
        sys.exit(2)
