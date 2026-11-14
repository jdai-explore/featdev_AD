"""
Skill & Validator: Change Request Impact Analyzer
Traverses the SQLite traceability graph to calculate ripple effects of parameter updates,
flags stale artifacts, and prescribes the exact agent re-invocation order.
"""

import sys
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List

def analyze_change_impact(
    db_path: Path,
    changed_node_id: str,
    change_reason: str,
    output_report_path: Path
) -> Dict[str, Any]:
    if not db_path.exists():
        return {"status": "FAIL", "error": f"Database not found: {db_path}"}

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get changed node info
    cur.execute("SELECT node_id, phase, artifact_path, title FROM trace_nodes WHERE node_id = ?", (changed_node_id,))
    target_node = cur.fetchone()
    if not target_node:
        conn.close()
        return {"status": "FAIL", "error": f"Node ID {changed_node_id} not found in traceability graph."}

    # Recursive downstream traversal
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
    """, (changed_node_id,))

    downstream_rows = cur.fetchall()

    impacted_list: List[Dict[str, Any]] = []
    agent_map = {
        "Phase 3: Activation": "Agent 03 (Feature Activation)",
        "Phase 4: HMI": "Agent 04 (Human Factors & HMI)",
        "Phase 5: Safety": "Agent 05 (Safety, SOTIF & AI Safety)",
        "Phase 6: E/E Arch": "Agent 06 (System & E/E Architect)",
        "Phase 7: Scenarios": "Agent 07 (Scenario & Sim Orchestrator)",
        "Phase 8: MBD Code": "Agent 08 (MBD & Verification)",
        "Phase 8: Validation": "Agent 08 (MBD & Verification)"
    }

    prescribed_agents = []

    # Update statuses to STALE
    for r in downstream_rows:
        target_id, phase, artifact, title, rel, depth = r
        cur.execute("UPDATE trace_nodes SET status = 'STALE' WHERE node_id = ?", (target_id,))
        impacted_list.append({
            "target_id": target_id,
            "phase": phase,
            "artifact_path": artifact,
            "title": title,
            "relation": rel,
            "depth": depth,
            "responsible_agent": agent_map.get(phase, "Systems Engineering Lead")
        })
        resp_agent = agent_map.get(phase)
        if resp_agent and resp_agent not in prescribed_agents:
            prescribed_agents.append(resp_agent)

    conn.commit()
    conn.close()

    # Generate Markdown Report
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    report_content = f"""# Change Request Impact Assessment Report
**Target Node Modified:** `{target_node[0]}` ({target_node[3]})  
**Artifact Path:** `{target_node[2]}`  
**Phase:** `{target_node[1]}`  
**Change Description:** {change_reason}  

---

### 1. Downstream Traceability Graph Traversal (`kg5_traceability.sqlite`)
The following connected engineering artifacts are automatically flagged as **STALE** and require re-execution and human re-sign-off:

| Trace ID | Phase | Affected Artifact | Relationship | Depth | Responsible Agent |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for item in impacted_list:
        report_content += f"| `{item['target_id']}` | {item['phase']} | `{item['artifact_path']}` | {item['relation']} | {item['depth']} | {item['responsible_agent']} |\n"

    report_content += f"""
---

### 2. Prescribed Re-Execution Workflow Sequence
To re-establish automotive safety compliance (ISO 26262 / ISO 21448 / UN R157), execute the following agents sequentially:
"""
    for idx, ag in enumerate(prescribed_agents, start=1):
        report_content += f"{idx}. **{ag}** -> Re-generate artifact, run pre-review gatekeeper, and sign off.\n"

    report_content += """
---
### 3. Gatekeeper Status
* **Pre-Review Gatekeeper Decision:** `BLOCKED` (Dependent artifacts are marked `STALE`)
* **Next Action:** Invoke the first prescribed agent in the sequence.
"""

    with open(output_report_path, "w", encoding="utf-8") as rf:
        rf.write(report_content)

    return {
        "status": "PASS",
        "changed_node": target_node[0],
        "stale_artifacts_count": len(impacted_list),
        "impacted_artifacts": impacted_list,
        "prescribed_agents_sequence": prescribed_agents,
        "report_file": str(output_report_path)
    }

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Usage: change_impact_analyzer.py <db_path> <node_id> <reason> <output_report_md>"}))
        sys.exit(1)

    res = analyze_change_impact(Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    print(json.dumps(res, indent=2))
