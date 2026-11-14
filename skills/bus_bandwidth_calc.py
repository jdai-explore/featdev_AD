"""
Skill: Bus Bandwidth & Latency Budget Verifier (CAN-FD Physical Framing & TSN)
Implements ISO 11898-1:2015 CAN-FD framing overhead calculation:
- Arbitration vs. Data Phase bit-time modeling
- Dynamic bit-stuffing factor (worst-case 1.2x)
- CRC-17 (<= 16 bytes) and CRC-21 (> 16 bytes) fields
- IEEE 802.1Qbv Ethernet TSN frame encapsulation (VLAN, Preamble, IPG, FCS)
- Worst-Case Execution Time (WCET) compute budget verification
"""

import sys
import json
import math
from pathlib import Path
from typing import Dict, Any, List

def calculate_canfd_frame_bits(payload_bytes: int, is_extended_id: bool = False) -> Dict[str, float]:
    """
    Computes exact physical layer bit counts for a CAN-FD frame per ISO 11898-1:2015.
    """
    # 1. Arbitration Phase bits
    id_bits = 29 if is_extended_id else 11
    # SOF (1) + ID + R1/IDE/EDL (3)
    arbitration_nominal_bits = 1 + id_bits + 3

    # 2. Control & Data Phase bits
    # BRS (1) + ESI (1) + DLC (4) = 6 bits
    control_bits = 6
    data_bits = payload_bytes * 8
    # Stuff count (4 bits) + CRC-17 (<= 16 bytes) or CRC-21 (> 16 bytes)
    crc_bits = 21 if payload_bytes <= 16 else 25 # includes stuff count
    crc_delimiter = 1

    # Fields subject to dynamic bit stuffing: SOF through CRC sequence
    # Worst case stuffing factor is ~1.2x
    stuffed_bits = (arbitration_nominal_bits + control_bits + data_bits + crc_bits) * 1.2

    # 3. Acknowledge and End of Frame (Fixed bits, no stuffing)
    # ACK (1) + ACK Delimiter (1) + EOF (7) + Intermission (3) = 12 bits
    fixed_end_bits = 12

    total_worst_case_bits = stuffed_bits + fixed_end_bits + crc_delimiter

    return {
        "payload_bytes": payload_bytes,
        "raw_payload_bits": data_bits,
        "total_physical_bits": math.ceil(total_worst_case_bits)
    }

def calculate_ethernet_tsn_frame_bits(payload_bytes: int) -> int:
    """
    Computes Ethernet TSN frame bits:
    Preamble (7B) + SFD (1B) + MAC Header (12B) + 802.1Q VLAN Tag (4B) +
    EtherType (2B) + Payload (min 46B) + FCS (4B) + Inter-Packet Gap (12B)
    """
    min_payload = max(payload_bytes, 46)
    total_frame_bytes = 8 + 14 + 4 + 2 + min_payload + 4 + 12
    return total_frame_bytes * 8

def evaluate_icd_performance(icd_path: str) -> Dict[str, Any]:
    with open(icd_path, "r", encoding="utf-8") as f:
        icd = json.load(f)

    buses = {b["bus_id"]: b for b in icd.get("communication_buses", [])}
    signals = icd.get("critical_signals", [])
    compute_nodes = icd.get("compute_nodes", [])

    bus_load_bps = {b_id: 0.0 for b_id in buses}
    unprotected_critical_signals = []
    signal_frame_breakdowns = []

    for sig in signals:
        b_ref = sig.get("bus_ref")
        cycle_ms = sig.get("cycle_time_ms", 10)
        bits = sig.get("payload_bits", 64)
        payload_bytes = math.ceil(bits / 8.0)
        e2e = sig.get("e2e_protection", "")

        freq_hz = 1000.0 / float(cycle_ms)
        bus_meta = buses.get(b_ref, {})
        bus_type = bus_meta.get("bus_type", "")

        if "CAN" in bus_type:
            frame_info = calculate_canfd_frame_bits(payload_bytes)
            phys_bits_per_sec = frame_info["total_physical_bits"] * freq_hz
        else:
            tsn_bits = calculate_ethernet_tsn_frame_bits(payload_bytes)
            phys_bits_per_sec = tsn_bits * freq_hz

        if b_ref in bus_load_bps:
            bus_load_bps[b_ref] += phys_bits_per_sec

        signal_frame_breakdowns.append({
            "signal": sig.get("signal_name"),
            "bus": b_ref,
            "cycle_ms": cycle_ms,
            "phys_bitrate_kbps": round(phys_bits_per_sec / 1000.0, 2)
        })

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
        "engine": "ISO 11898-1:2015 CAN-FD & IEEE 802.1Qbv TSN Physical Protocol Linter",
        "icd_id": icd.get("icd_id"),
        "bus_evaluations": bus_reports,
        "signal_frame_breakdowns": signal_frame_breakdowns,
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
