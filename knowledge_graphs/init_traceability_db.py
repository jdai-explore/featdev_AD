"""
Initializes and populates KG5: End-to-End Relational Traceability Database (kg5_traceability.sqlite).
Implements bi-directional traceability graph connecting:
  Legal Clauses -> Requirements -> ODD -> HMI -> Safety Goals -> Architecture/ICD -> Code -> Scenarios -> Test Validation.
"""

import sqlite3
from pathlib import Path

def init_db(db_path: Path):
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE trace_nodes (
        node_id TEXT PRIMARY KEY,
        phase TEXT NOT NULL,
        artifact_path TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'APPROVED',
        sha256_hash TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE trace_edges (
        edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        FOREIGN KEY(source_id) REFERENCES trace_nodes(node_id),
        FOREIGN KEY(target_id) REFERENCES trace_nodes(node_id)
    );
    """)

    # Populate baseline nodes
    nodes = [
        ("REQ-REG-UN-R171", "Phase 1: Regulatory", "artifacts/01_compliance_matrix.csv", "UN R171 DCAS Compliance Mandate", "APPROVED", "hash_reg_01"),
        ("REQ-REG-UN-R157", "Phase 1: Regulatory", "artifacts/01_compliance_matrix.csv", "UN R157 ALKS L3 Highway Pilot", "APPROVED", "hash_reg_02"),
        ("ODD-SPEC-001", "Phase 2: ODD", "artifacts/02_lane_centering_odd.yaml", "Highway Operational Design Domain Spec", "APPROVED", "hash_odd_01"),
        ("AUTH-SUB-001", "Phase 3: Activation", "artifacts/03_subscription_ota.puml", "Graceful Session Lock & Offline Lease", "APPROVED", "hash_auth_01"),
        ("HMI-STATE-001", "Phase 4: HMI", "artifacts/04_hmi_state_matrix.csv", "Transition of Control & MRM State Machine", "APPROVED", "hash_hmi_01"),
        ("SAF-HARA-001", "Phase 5: Safety", "artifacts/05_safety_analysis.csv", "Lateral Steering Overfeed Hazard (ASIL D)", "APPROVED", "hash_saf_01"),
        ("SAF-SOTIF-001", "Phase 5: Safety", "artifacts/05_safety_analysis.csv", "Low-Sun Glare Camera Degradation Trigger", "APPROVED", "hash_saf_02"),
        ("ARCH-ICD-001", "Phase 6: E/E Arch", "artifacts/06_vehicle_arch_icd.json", "Fail-Operational Dual Compute & DSSAD Bus", "APPROVED", "hash_arch_01"),
        ("SCEN-XOSC-001", "Phase 7: Scenarios", "artifacts/07_scenarios/cutin_glare.xosc", "ASAM OpenSCENARIO Low Sun Glare Cut-In", "APPROVED", "hash_scen_01"),
        ("CODE-CTRL-001", "Phase 8: MBD Code", "artifacts/08_lane_controller.c", "MISRA-C Compliant Steering Actuator Interface", "APPROVED", "hash_code_01"),
        ("VAL-TEST-001", "Phase 8: Validation", "artifacts/08_validation_report.md", "SiL / CARLA Deterministic KPI Pass Report", "APPROVED", "hash_val_01")
    ]

    cur.executemany("INSERT INTO trace_nodes VALUES (?, ?, ?, ?, ?, ?)", nodes)

    # Populate baseline edges
    edges = [
        ("REQ-REG-UN-R157", "ODD-SPEC-001", "CONSTRAINS"),
        ("REQ-REG-UN-R171", "ODD-SPEC-001", "CONSTRAINS"),
        ("ODD-SPEC-001", "AUTH-SUB-001", "GOVERNS_ACCESS"),
        ("ODD-SPEC-001", "HMI-STATE-001", "TRIGGERS_TRANSITIONS"),
        ("ODD-SPEC-001", "SAF-SOTIF-001", "DEFINES_LIMITS"),
        ("HMI-STATE-001", "ARCH-ICD-001", "MAPS_TO_DSSAD_SIGNALS"),
        ("SAF-HARA-001", "ARCH-ICD-001", "ALLOCATES_REDUNDANCY"),
        ("SAF-SOTIF-001", "SCEN-XOSC-001", "SYNTHESIZES_TEST_CASE"),
        ("ARCH-ICD-001", "CODE-CTRL-001", "IMPLEMENTS_INTERFACES"),
        ("SCEN-XOSC-001", "VAL-TEST-001", "TESTS_IN_SIMULATION"),
        ("CODE-CTRL-001", "VAL-TEST-001", "VERIFIED_BY")
    ]

    cur.executemany("INSERT INTO trace_edges (source_id, target_id, relation_type) VALUES (?, ?, ?)", edges)

    conn.commit()
    conn.close()
    print(f"[SUCCESS] Traceability database initialized at: {db_path}")

if __name__ == "__main__":
    db_file = Path(__file__).resolve().parent / "kg5_traceability.sqlite"
    init_db(db_file)
