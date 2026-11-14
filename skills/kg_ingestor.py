"""
Skill: Regulatory & Standards Knowledge Graph Ingestor & Semantic Search Engine
Ingests and indexes UNECE (UN R157, R171, R155, R156), ISO (26262, 21448, 8800),
German StVG/AFGBV, and EU AI Act into SQLite FTS5 for fast, deterministic, offline retrieval.
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parent.parent

class RegulatoryKGIngestor:
    def __init__(self, db_path: Optional[Path] = None, json_kg_path: Optional[Path] = None):
        self.db_path = db_path or (ROOT / "knowledge_graphs/kg1_regulatory.sqlite")
        self.json_kg_path = json_kg_path or (ROOT / "knowledge_graphs/kg1_regulatory.json")

    def init_fts_db(self):
        """Initializes SQLite FTS5 table for full-text search indexing."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS regulatory_clauses (
            clause_id TEXT PRIMARY KEY,
            standard_id TEXT NOT NULL,
            standard_title TEXT NOT NULL,
            target_levels TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            mandatory_artifacts TEXT NOT NULL
        );
        """)
        cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_clauses USING fts5(
            clause_id,
            standard_id,
            title,
            summary
        );
        """)
        conn.commit()
        conn.close()

    def ingest_from_json(self) -> int:
        """Ingests all regulations from JSON into the relational and FTS5 tables."""
        if not self.json_kg_path.exists():
            return 0

        self.init_fts_db()
        with open(self.json_kg_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        count = 0
        for reg in data.get("regulations", []):
            std_id = reg.get("standard_id", "")
            std_title = reg.get("full_title", "")
            levels_str = ",".join(reg.get("target_levels", []))

            for clause in reg.get("clauses", []):
                cid = clause.get("clause_id", "")
                title = clause.get("title", "")
                summary = clause.get("requirement_summary", "")
                artifacts_str = ",".join(clause.get("mandatory_artifacts", []))

                cur.execute("""
                INSERT INTO regulatory_clauses (clause_id, standard_id, standard_title, target_levels, title, summary, mandatory_artifacts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(clause_id) DO UPDATE SET
                    standard_id=excluded.standard_id,
                    standard_title=excluded.standard_title,
                    target_levels=excluded.target_levels,
                    title=excluded.title,
                    summary=excluded.summary,
                    mandatory_artifacts=excluded.mandatory_artifacts;
                """, (cid, std_id, std_title, levels_str, title, summary, artifacts_str))
                count += 1

        # Rebuild FTS index
        cur.execute("DELETE FROM fts_clauses;")
        cur.execute("""
        INSERT INTO fts_clauses(rowid, clause_id, standard_id, title, summary)
        SELECT rowid, clause_id, standard_id, title, summary FROM regulatory_clauses;
        """)

        conn.commit()
        conn.close()
        return count

    def search_clauses(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches clauses using SQLite FTS5 rank ordering."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Sanitize query for FTS5 (replace special characters with spaces)
        clean_q = "".join(c if c.isalnum() else " " for c in query).strip()
        tokens = [t for t in clean_q.split() if len(t) > 2]
        if not tokens:
            conn.close()
            return []

        fts_match_expr = " OR ".join(f'"{t}"*' for t in tokens)

        try:
            cur.execute("""
            SELECT r.clause_id, r.standard_id, r.standard_title, r.target_levels, r.title, r.summary, r.mandatory_artifacts, bm25(fts_clauses) as rank
            FROM fts_clauses f
            JOIN regulatory_clauses r ON f.clause_id = r.clause_id
            WHERE fts_clauses MATCH ?
            ORDER BY rank
            LIMIT ?;
            """, (fts_match_expr, limit))
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Fallback to LIKE
            cur.execute("""
            SELECT clause_id, standard_id, standard_title, target_levels, title, summary, mandatory_artifacts, 0.0
            FROM regulatory_clauses
            WHERE summary LIKE ? OR title LIKE ?
            LIMIT ?;
            """, (f"%{tokens[0]}%", f"%{tokens[0]}%", limit))
            rows = cur.fetchall()

        results = [
            {
                "clause_id": r[0],
                "standard_id": r[1],
                "standard_title": r[2],
                "target_levels": r[3].split(","),
                "title": r[4],
                "summary": r[5],
                "mandatory_artifacts": r[6].split(","),
                "relevance_rank": r[7]
            }
            for r in rows
        ]

        conn.close()
        return results

if __name__ == "__main__":
    from typing import Optional
    parser = argparse.ArgumentParser(description="Regulatory Knowledge Graph Ingestor & Search")
    parser.add_argument("--ingest", action="store_true", help="Ingest KG1 JSON into SQLite FTS5")
    parser.add_argument("--search", type=str, help="Search clauses via FTS5 BM25")

    args = parser.parse_args()
    ingestor = RegulatoryKGIngestor()

    if args.ingest or not ingestor.db_path.exists():
        count = ingestor.ingest_from_json()
        print(f"[INGEST] Ingested {count} regulatory clauses into {ingestor.db_path.name}")

    if args.search:
        hits = ingestor.search_clauses(args.search)
        print(json.dumps(hits, indent=2))
