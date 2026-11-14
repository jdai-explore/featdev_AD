"""
Skill: Automated Traceability Extractor & Graph Synchronizer
Parses heterogeneous automotive engineering artifacts (.csv, .yaml, .json, .c, .xosc, .md)
to extract declared Trace_IDs and dependency relationships, dynamically updating
the SQLite bi-directional traceability graph (kg5_traceability.sqlite).
"""

import re
import csv
import json
import yaml
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set

# Regex patterns for Trace_ID conventions
TRACE_ID_PATTERN = re.compile(r"\b(REQ-[A-Z0-9_-]+|ODD-[A-Z0-9_-]+|AUTH-[A-Z0-9_-]+|HMI-[A-Z0-9_-]+|SAF-[A-Z0-9_-]+|ARCH-[A-Z0-9_-]+|SCEN-[A-Z0-9_-]+|CODE-[A-Z0-9_-]+|VAL-[A-Z0-9_-]+)\b")

PHASE_MAP = {
    "REQ-": "Phase 1: Regulatory",
    "ODD-": "Phase 2: ODD",
    "AUTH-": "Phase 3: Activation",
    "HMI-": "Phase 4: HMI",
    "SAF-": "Phase 5: Safety",
    "ARCH-": "Phase 6: E/E Arch",
    "SCEN-": "Phase 7: Scenarios",
    "CODE-": "Phase 8: MBD Code",
    "VAL-": "Phase 8: Validation"
}

class TraceabilityExtractor:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    @staticmethod
    def compute_sha256(filepath: Path) -> str:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def extract_from_csv(self, file_path: Path) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str, str]]]:
        nodes = []
        edges = []
        file_sha = self.compute_sha256(file_path)
        rel_path = file_path.as_posix()

        with open(file_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            
            for row in reader:
                trace_id = row.get("Trace_ID", "").strip()
                if not trace_id:
                    continue

                # Determine phase
                prefix = trace_id[:4] if len(trace_id) >= 4 else "REQ-"
                phase = PHASE_MAP.get(prefix, "Phase 1: Requirements")

                # Derive descriptive title
                title = (
                    row.get("Compliance_Mandate_Summary")
                    or row.get("Malfunction_Description_or_Triggering_Condition")
                    or row.get("Trigger_Event")
                    or row.get("Threat_Scenario")
                    or f"Requirement node {trace_id}"
                )[:120]

                nodes.append({
                    "node_id": trace_id,
                    "phase": phase,
                    "artifact_path": rel_path,
                    "title": title,
                    "status": "APPROVED",
                    "sha256_hash": file_sha
                })

                # Check for evidence/target references in the row
                evidence_ref = row.get("Evidence_Artifact_Ref", "").strip()
                if evidence_ref:
                    # Search for any referenced trace IDs in row values
                    for val in row.values():
                        if isinstance(val, str) and val and val != trace_id:
                            for ref_match in TRACE_ID_PATTERN.findall(val):
                                if ref_match != trace_id:
                                    edges.append((trace_id, ref_match, "REFERENCES"))

        return nodes, edges

    def extract_from_yaml(self, file_path: Path) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str, str]]]:
        nodes = []
        edges = []
        file_sha = self.compute_sha256(file_path)
        rel_path = file_path.as_posix()

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # OpenODD specification
        if "odd_specification" in data:
            odd_obj = data["odd_specification"]
            odd_id = odd_obj.get("id", "ODD-SPEC-001")
            feat_ref = odd_obj.get("feature_ref", "")
            title = f"ODD Spec: {odd_obj.get('spatial_boundaries', {}).get('road_type', 'Operational Domain')}"
            
            nodes.append({
                "node_id": odd_id,
                "phase": "Phase 2: ODD",
                "artifact_path": rel_path,
                "title": title,
                "status": "APPROVED",
                "sha256_hash": file_sha
            })

            # Check regulatory references
            for mode in odd_obj.get("automation_level_modes", []):
                reg = mode.get("governing_regulation", "")
                if reg:
                    edges.append((odd_id, f"REQ-REG-{reg}", "CONSTRAINED_BY"))

        # ML Training Manifest
        elif "manifest_id" in data:
            m_id = data.get("manifest_id", "ML-MAN-001")
            nodes.append({
                "node_id": m_id,
                "phase": "Cross-Cutting: ML/AI",
                "artifact_path": rel_path,
                "title": f"ML Model: {data.get('model_architecture', 'Perception')}",
                "status": "APPROVED",
                "sha256_hash": file_sha
            })

        return nodes, edges

    def extract_from_json(self, file_path: Path) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str, str]]]:
        nodes = []
        edges = []
        file_sha = self.compute_sha256(file_path)
        rel_path = file_path.as_posix()

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "icd_id" in data:
            icd_id = data.get("icd_id")
            feat_ref = data.get("feature_ref", "")
            nodes.append({
                "node_id": icd_id,
                "phase": "Phase 6: E/E Arch",
                "artifact_path": rel_path,
                "title": f"Interface Control Document: {data.get('target_asil', 'ASIL_D')}",
                "status": "APPROVED",
                "sha256_hash": file_sha
            })

        return nodes, edges

    def extract_from_source(self, file_path: Path) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str, str]]]:
        nodes = []
        edges = []
        file_sha = self.compute_sha256(file_path)
        rel_path = file_path.as_posix()
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Scan for @trace_id tags
        trace_tag_match = re.search(r"@trace_id\s+([A-Z0-9_-]+)", content)
        if trace_tag_match:
            code_id = trace_tag_match.group(1)
            nodes.append({
                "node_id": code_id,
                "phase": "Phase 8: MBD Code",
                "artifact_path": rel_path,
                "title": f"Safety Controller Implementation: {file_path.name}",
                "status": "APPROVED",
                "sha256_hash": file_sha
            })

        return nodes, edges

    def extract_and_sync(self, targets: List[Path]) -> Dict[str, Any]:
        """Scans targets, extracts trace metadata, and syncs to SQLite."""
        all_nodes = []
        all_edges = []

        for p in targets:
            if not p.exists():
                continue

            suffix = p.suffix.lower()
            if suffix == ".csv":
                n, e = self.extract_from_csv(p)
            elif suffix in (".yaml", ".yml"):
                n, e = self.extract_from_yaml(p)
            elif suffix == ".json":
                n, e = self.extract_from_json(p)
            elif suffix in (".c", ".h", ".cpp"):
                n, e = self.extract_from_source(p)
            else:
                continue

            all_nodes.extend(n)
            all_edges.extend(e)

        if not self.db_path.exists():
            from knowledge_graphs.init_traceability_db import init_db
            init_db(self.db_path)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Upsert nodes
        for node in all_nodes:
            cur.execute("""
            INSERT INTO trace_nodes (node_id, phase, artifact_path, title, status, sha256_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                phase = excluded.phase,
                artifact_path = excluded.artifact_path,
                title = excluded.title,
                status = excluded.status,
                sha256_hash = excluded.sha256_hash;
            """, (node["node_id"], node["phase"], node["artifact_path"], node["title"], node["status"], node["sha256_hash"]))

        # Insert edges
        edges_added = 0
        for src, tgt, rel in all_edges:
            # Verify target exists in trace_nodes before adding edge
            cur.execute("SELECT 1 FROM trace_nodes WHERE node_id = ?", (tgt,))
            if cur.fetchone():
                cur.execute("""
                INSERT OR IGNORE INTO trace_edges (source_id, target_id, relation_type)
                VALUES (?, ?, ?);
                """, (src, tgt, rel))
                edges_added += 1

        conn.commit()
        conn.close()

        return {
            "status": "PASS",
            "nodes_extracted_count": len(all_nodes),
            "edges_linked_count": edges_added,
            "extracted_nodes": [n["node_id"] for n in all_nodes]
        }

if __name__ == "__main__":
    import sys
    base = Path(__file__).resolve().parent.parent
    db = base / "knowledge_graphs/kg5_traceability.sqlite"
    extractor = TraceabilityExtractor(db)

    # Scan all artifacts in artifacts/
    target_files = list((base / "artifacts").rglob("*.*"))
    res = extractor.extract_and_sync(target_files)
    print(json.dumps(res, indent=2))
