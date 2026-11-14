"""
Skill: SQLite & Knowledge Graph Traverser
Executes structured deterministic queries across the 5 automotive domain knowledge graphs
without blowing up LLM context windows or scraping external networks.
"""

import sys
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List

def query_traceability(db_path: str, source_trace_id: str) -> Dict[str, Any]:
    """Traverses downstream and upstream dependencies for a given Trace_ID."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Downstream dependencies
    cur.execute("""
    WITH RECURSIVE downstream AS (
        SELECT target_id, relation_type, 1 AS depth
        FROM trace_edges
        WHERE source_id = ?
        UNION ALL
        SELECT e.target_id, e.relation_type, d.depth + 1
        FROM trace_edges e
        JOIN downstream d ON e.source_id = d.target_id
        WHERE d.depth < 10
    )
    SELECT d.target_id, n.phase, n.artifact_path, n.title, d.relation_type, d.depth
    FROM downstream d
    JOIN trace_nodes n ON d.target_id = n.node_id
    ORDER BY d.depth;
    """, (source_trace_id,))

    downstream_impact = [
        {"target_id": row[0], "phase": row[1], "artifact": row[2], "title": row[3], "relation": row[4], "depth": row[5]}
        for row in cur.fetchall()
    ]

    # Node detail
    cur.execute("SELECT node_id, phase, artifact_path, title, status FROM trace_nodes WHERE node_id = ?", (source_trace_id,))
    node_row = cur.fetchone()
    node_info = {
        "node_id": node_row[0], "phase": node_row[1], "artifact": node_row[2], "title": node_row[3], "status": node_row[4]
    } if node_row else None

    conn.close()
    return {
        "query_source_id": source_trace_id,
        "node_info": node_info,
        "downstream_impact_count": len(downstream_impact),
        "downstream_artifacts_impacted": downstream_impact
    }

def query_regulatory_kg(kg1_path: str, standard_id: str) -> Dict[str, Any]:
    with open(kg1_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for reg in data.get("regulations", []):
        if reg.get("standard_id") == standard_id:
            return reg
    return {"error": f"Standard {standard_id} not found in KG1."}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: sqlite_kg_traverser.py <trace|reg> <path> <id>"}))
        sys.exit(1)

    mode = sys.argv[1]
    path_arg = sys.argv[2]
    id_arg = sys.argv[3] if len(sys.argv) > 3 else ""

    if mode == "trace":
        res = query_traceability(path_arg, id_arg)
        print(json.dumps(res, indent=2))
    elif mode == "reg":
        res = query_regulatory_kg(path_arg, id_arg)
        print(json.dumps(res, indent=2))
    else:
        print(json.dumps({"error": f"Unknown mode: {mode}"}))
        sys.exit(1)
