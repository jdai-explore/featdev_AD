"""
Skill: Bus Bandwidth & Latency Budget Verifier
Validates vehicle network utilization (Ethernet TSN, CAN-FD) and WCET latency
to guarantee fail-operational communication without message starvation.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

def evaluate_icd_performance(icd_path: str) -> Dict[str, Any]:
    with open(icd_path, "r", encoding="utf-8") as f:
        icd = json.load(f)

    buses = {b["bus_id"]: b for b in icd.get("communication_buses", [])}
    signals = icd.get("critical_signals", [])
    compute_nodes = icd.get("compute_nodes", [])

    bus_load_bps = {b_id: 0.0 for b_id in buses}
    unprotected_critical_signals = []

    for sig in signals:
        b_ref = sig.get("bus_ref")
        cycle_ms = sig.get("cycle_time_ms", 10)
        bits = sig.get("payload_bits", 64)
        e2e = sig.get("e2e_protection", "")

        # Frequency in Hz
        freq_hz = 1000.0 / float(cycle_ms)
        data_rate_bps = bits * freq_hz

        if b_ref in bus_load_bps:
            bus_load_bps[b_ref] += data_rate_bps

        if not e2e or "CRC" not in e2e:
            unprotected_critical_signals.append(sig.get("signal_name"))

    bus_reports = []
    has_overload = False

    for b_id, b_meta in buses.items():
        capacity_bps = b_meta["bandwidth_mbps"] * 1_000_000.0
        actual_bps = bus_load_bps.get(b_id, 0.0)
        util_pct = (actual_bps / capacity_bps) * 100.0
        max_allowed_pct = b_meta.get("max_utilization_pct", 70.0)

        is_violating = util_pct > max_allowed_pct
        if is_violating:
            has_overload = True

        bus_reports.append({
            "bus_id": b_id,
            "bus_type": b_meta.get("bus_type"),
            "bandwidth_mbps": b_meta.get("bandwidth_mbps"),
            "consumed_kbps": round(actual_bps / 1000.0, 2),
            "utilization_pct": round(util_pct, 4),
            "max_allowed_pct": max_allowed_pct,
            "status": "OVERLOAD_FAIL" if is_violating else "PASS"
        })

    # Validate WCET compute budgets
    wcet_issues = []
    for node in compute_nodes:
        budget = node.get("wcet_budget_ms", 100.0)
        if budget > 50.0 and "PRIMARY" in node.get("role", ""):
            wcet_issues.append(f"Node {node['node_id']} exceeds 50.0ms primary control loop limit (has {budget}ms)")

    overall_status = "FAIL" if (has_overload or unprotected_critical_signals or wcet_issues) else "PASS"

    return {
        "status": overall_status,
        "icd_id": icd.get("icd_id"),
        "bus_evaluations": bus_reports,
        "unprotected_signals": unprotected_critical_signals,
        "wcet_issues": wcet_issues
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: bus_bandwidth_calc.py <icd_json_path>"}))
        sys.exit(1)

    res = evaluate_icd_performance(sys.argv[1])
    print(json.dumps(res, indent=2))
    if res["status"] != "PASS":
        sys.exit(2)
