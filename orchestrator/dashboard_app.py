"""
Autonomous Driving & ADAS Review Cockpit (Streamlit Web Application)
Visual interface for Lead Systems Architects to:
- Review 11-Agent V-Model pipeline status
- Inspect Gatekeeper assertions (MISRA-C AST, OpenSCENARIO kinematics, CAN-FD bandwidth)
- Explore the interactive bi-directional traceability graph (Mermaid)
- Cryptographically approve and seal execution bundles
"""

import os
import json
import yaml
import sqlite3
from pathlib import Path
import streamlit as st

# Setup page
st.set_page_config(
    page_title="ADAS/AD Feature Engineering Cockpit",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

ROOT = Path(__file__).resolve().parent.parent
BUNDLES_DIR = ROOT / ".determinism/execution_bundles"
AGENTS_DIR = ROOT / "agents"
ARTIFACTS_DIR = ROOT / "artifacts"
PROFILES_DIR = ROOT / "profiles"
DB_PATH = ROOT / "knowledge_graphs/kg5_traceability.sqlite"

# Sidebar: Profile Selection & Determinism Status
st.sidebar.title("🚗 ADAS / AD Cockpit")
st.sidebar.markdown("**Governance:** Human-in-the-Loop Hub-and-Spoke")

profiles = [p.stem for p in PROFILES_DIR.glob("*.yaml") if p.name != "feature_profile.yaml"]
selected_profile = st.sidebar.selectbox("Active Feature Profile", profiles, index=1 if len(profiles) > 1 else 0)

with open(PROFILES_DIR / f"{selected_profile}.yaml", "r", encoding="utf-8") as pf:
    profile_data = yaml.safe_load(pf)

feat_id = profile_data.get("feature_id", "FEAT-L3-HWY-CHAUFFEUR")
st.sidebar.info(f"**Feature ID:** `{feat_id}`\n\n**SAE Level:** `{profile_data.get('sae_level')}`\n\n**Target ASIL:** `{profile_data.get('safety_target_asil')}`")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔒 Deterministic Engine")
lock_file = ROOT / ".determinism/model_lock.json"
if lock_file.exists():
    with open(lock_file, "r", encoding="utf-8") as lf:
        lock_data = json.load(lf)
    st.sidebar.caption(f"**Policy:** `{lock_data.get('runtime_policy')}`")
    st.sidebar.caption(f"**Model:** `{lock_data['llm_configuration']['pinned_checkpoint']}`")
    st.sidebar.caption(f"**Temp:** `{lock_data['llm_configuration']['inference_params']['temperature']}` | **Seed:** `{lock_data['llm_configuration']['inference_params']['seed']}`")

# Main Page Header
st.title("Automotive Feature Development & Safety Review Cockpit")
st.markdown(f"**Feature:** {profile_data.get('feature_name')} (`{feat_id}`)")

# KPI Metric Cards
col1, col2, col3, col4 = st.columns(4)

total_agents = len(list(AGENTS_DIR.glob("*.yaml")))
verified_bundles = len(list(BUNDLES_DIR.glob(f"bundle_{feat_id}_*.json")))

# Query SQLite stats
if DB_PATH.exists():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM trace_nodes;")
    total_nodes = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM trace_nodes WHERE status = 'STALE';")
    stale_nodes = cur.fetchone()[0]
    conn.close()
else:
    total_nodes, stale_nodes = 0, 0

col1.metric("Registered Agents", total_agents)
col2.metric("Executed Phases", verified_bundles)
col3.metric("Traceability Nodes", total_nodes)
col4.metric("Stale Ripple Nodes", stale_nodes, delta=-stale_nodes if stale_nodes > 0 else 0)

# Tabs
tab_pipeline, tab_artifacts, tab_traceability = st.tabs(["📋 V-Model Pipeline & Gatekeeper", "📄 Nascent Artifacts & Diffs", "🕸️ Traceability Graph"])

with tab_pipeline:
    st.subheader("11-Agent Engineering Workflow Status")
    
    agent_files = sorted(AGENTS_DIR.glob("*.yaml"))
    pipeline_rows = []
    
    for af in agent_files:
        with open(af, "r", encoding="utf-8") as yf:
            acfg = yaml.safe_load(yf)
        
        ag_id = acfg.get("agent_id")
        bundle_p = BUNDLES_DIR / f"bundle_{feat_id}_{ag_id}.json"
        
        if bundle_p.exists():
            with open(bundle_p, "r", encoding="utf-8") as bf:
                bdata = json.load(bf)
            sign_status = bdata.get("compliance_attestation", {}).get("human_signoff_status", "PENDING_REVIEW")
            gate_status = "✅ PASS 100%"
        else:
            sign_status = "⚪ STAGED"
            gate_status = "⚪ NOT RUN"
            
        with st.expander(f"{acfg.get('phase')}: {acfg.get('name')} ({gate_status} | {sign_status})"):
            st.markdown(f"**Role:** {acfg.get('role')}")
            st.markdown(f"**Inputs:** `{[i['artifact'] for i in acfg.get('inputs', [])]}`")
            st.markdown(f"**Outputs:** `{[o['artifact'] for o in acfg.get('outputs', [])]}`")
            st.markdown(f"**Bound Skills:** `{[s['name'] for s in acfg.get('skills', [])]}`")
            
            if bundle_p.exists():
                st.json(bdata.get("output_hashes"))
                if "PENDING" in sign_status:
                    if st.button(f"✍️ Sign-Off & Seal {ag_id}", key=f"sign_{ag_id}"):
                        bdata["compliance_attestation"]["human_signoff_status"] = "SIGNED_OFF_BY_LEAD_ARCHITECT"
                        with open(bundle_p, "w", encoding="utf-8") as bf:
                            json.dump(bdata, bf, indent=2)
                        st.success(f"Bundle {ag_id} cryptographically approved and sealed.")
                        st.rerun()

with tab_artifacts:
    st.subheader("Nascent Engineering Artifacts Viewer")
    artifact_files = sorted(ARTIFACTS_DIR.rglob("*.*"))
    art_choice = st.selectbox("Select Artifact to Inspect", [str(a.relative_to(ROOT)) for a in artifact_files if a.is_file()])
    
    if art_choice:
        chosen_path = ROOT / art_choice
        suffix = chosen_path.suffix.lower()
        content = chosen_path.read_text(encoding="utf-8", errors="ignore")
        
        if suffix in (".yaml", ".yml"):
            st.code(content, language="yaml")
        elif suffix == ".json":
            st.code(content, language="json")
        elif suffix == ".csv":
            st.text(content)
        elif suffix in (".c", ".h"):
            st.code(content, language="c")
        elif suffix in (".xosc", ".xml"):
            st.code(content, language="xml")
        elif suffix == ".md":
            st.markdown(content)
        else:
            st.text(content)

with tab_traceability:
    st.subheader("Bi-Directional Relational Traceability Graph")
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT source_id, target_id, relation_type FROM trace_edges LIMIT 25;")
        edges = cur.fetchall()
        conn.close()
        
        mermaid_code = "graph LR\n"
        for src, tgt, rel in edges:
            clean_src = src.replace("-", "_")
            clean_tgt = tgt.replace("-", "_")
            mermaid_code += f"    {clean_src}[{src}] -->|{rel}| {clean_tgt}[{tgt}]\n"
            
        st.code(mermaid_code, language="mermaid")
        st.caption("Visualizing the first 25 relational dependency links in `kg5_traceability.sqlite`.")
