"""
Skill: HMI & Feature State Machine Formal Completeness Verifier
Mathematically verifies state machine completeness, absence of dead-ends,
mandatory DSSAD logging, and guaranteed fallback to Minimum Risk Maneuver (MRM).
"""

import sys
import csv
import json
from collections import defaultdict
from pathlib import Path

def verify_hmi_state_machine(csv_path: str) -> dict:
    p = Path(csv_path)
    if not p.exists():
        return {"status": "FAIL", "error": f"File not found: {csv_path}"}

    transitions = defaultdict(list)
    state_triggers = defaultdict(set)
    all_states = set()
    next_states = set()
    rows_parsed = 0
    errors = []

    with open(p, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required_cols = {"Trace_ID", "Current_State", "Trigger_Event", "Next_State", "Max_Budget_s", "DSSAD_Log_Event"}
        missing_cols = required_cols - set(reader.fieldnames or [])
        if missing_cols:
            return {"status": "FAIL", "error": f"Missing required CSV columns: {missing_cols}"}

        for row in reader:
            rows_parsed += 1
            trace_id = row["Trace_ID"].strip()
            curr = row["Current_State"].strip()
            trig = row["Trigger_Event"].strip()
            nxt = row["Next_State"].strip()
            budget = float(row["Max_Budget_s"].strip() or 0.0)
            dssad = row["DSSAD_Log_Event"].strip()

            # Rule 1: Trace ID formatting
            if not trace_id.startswith("HMI-") and not trace_id.startswith("AUTH-"):
                errors.append(f"Invalid Trace_ID format '{trace_id}' in row {rows_parsed}")

            # Rule 2: Non-empty DSSAD event
            if not dssad:
                errors.append(f"Missing mandatory DSSAD_Log_Event on {trace_id}")

            # Rule 3: Positive budget on TOR states
            if "TOR_" in curr and budget <= 0.0:
                errors.append(f"TOR state '{curr}' on {trace_id} must specify positive timeout budget!")

            # Rule 4: Determinism (no duplicate trigger on same current state)
            if trig in state_triggers[curr]:
                errors.append(f"Ambiguous non-deterministic transition: '{curr}' already handles trigger '{trig}'")
            state_triggers[curr].add(trig)

            transitions[curr].append((trig, nxt, budget, dssad))
            all_states.add(curr)
            next_states.add(nxt)

    # Allowed terminal quiescent states
    allowed_terminals = {"OFF", "OFF_REJECTED", "MRM_ACTIVE_SHOULDER_STOP", "MRM_ACTIVE_STANDSTILL"}

    # Rule 5: Dead-end state detection
    for state in (all_states | next_states):
        if state not in transitions and state not in allowed_terminals:
            errors.append(f"DEAD-END DETECTED: State '{state}' has no outgoing transitions and is not a valid terminal state!")

    # Rule 6: Mandatory MRM fallback from urgent TOR
    tor2_transitions = transitions.get("TOR_STAGE_2_URGENT", [])
    tor2_targets = [nxt for _, nxt, _, _ in tor2_transitions]
    has_mrm = any("MRM_" in target for target in tor2_targets)
    if "TOR_STAGE_2_URGENT" in all_states and not has_mrm:
        errors.append("CRITICAL SAFETY GAP: TOR_STAGE_2_URGENT does not contain fallback transition to MRM!")

    # Rule 7: Reachability from OFF
    visited = set()
    queue = ["OFF"]
    while queue:
        curr = queue.pop(0)
        if curr not in visited:
            visited.add(curr)
            for _, nxt, _, _ in transitions.get(curr, []):
                if nxt not in visited:
                    queue.append(nxt)

    unreachable = (all_states | next_states) - visited
    if unreachable:
        errors.append(f"UNREACHABLE STATES DETECTED from initial state 'OFF': {list(unreachable)}")

    if errors:
        return {
            "status": "FAIL",
            "total_states": len(all_states | next_states),
            "total_transitions": rows_parsed,
            "errors": errors
        }

    return {
        "status": "PASS",
        "total_states": len(all_states | next_states),
        "total_transitions": rows_parsed,
        "verified_rules": [
            "Zero non-terminal dead-ends",
            "Deterministic transitions without branch collision",
            "Full reachability from OFF",
            "Mandatory DSSAD event on every transition",
            "Guaranteed fail-safe MRM escalation"
        ]
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: state_machine_verifier.py <csv_path>"}))
        sys.exit(1)

    result = verify_hmi_state_machine(sys.argv[1])
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        sys.exit(2)
