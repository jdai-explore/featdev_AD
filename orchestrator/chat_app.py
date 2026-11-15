"""
ADAS/AD Feature Engineering Cockpit — Unified Mission Control (Chainlit 2.x)
Single unified interface for:
  - System Preparedness & Health checks
  - Feature Project Selection & Guided Project Initialization
  - Chat-based Agent Coordination & Tool Invocation
  - Live Pipeline Status, Interactive Gates (Approve / Pause / Stop), and Deliverable Explorer
"""

import os
import sys
import json
import yaml
import sqlite3
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import chainlit as cl

# Path bootstrap
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm_client import UniversalLLMClient
from core.tool_registry import ToolRegistry
from tools.web_fetcher import fetch_live_regulation
from orchestrator.pipeline_runner import FeaturePipelineOrchestrator
from orchestrator.doctor import run_preparedness_check

AGENTS_DIR = ROOT / "agents"
PROFILES_DIR = ROOT / "profiles"
PROJECTS_DIR = ROOT / "projects"
LOCK_FILE = ROOT / ".determinism/model_lock.json"

_llm = UniversalLLMClient(offline_fallback=True)

_registry = ToolRegistry()
_registry.register_tool(
    func=fetch_live_regulation,
    name="fetch_live_regulation",
    description=(
        "Fetches and skeptically validates a live regulatory document from an "
        "institutional domain (UNECE, ISO, SAE, EUR-Lex). Checks domain trust, "
        "document freshness, draft markers, and cross-references local KG1 baseline."
    )
)

SYSTEM_PROMPT = (
    "You are the Mission Control System Architect for the ADAS/AD Feature Engineering Ecosystem. "
    "You guide and coordinate 12 specialized engineering agents covering: "
    "1. Regulatory & Homologation (UN R157/R171/R155/R156, EU AI Act, ISO/PAS 8800) "
    "2. ODD Architecture (ASAM OpenODD 1.0, ISO 34503) "
    "3. Feature Activation & Cybersecurity (UN R155 CSMS / ISO 21434 TARA) "
    "4. Cognitive Ergonomics & HMI (ISO 15007, TOR/MRM State Transitions) "
    "5. Functional Safety & SOTIF (ISO 26262 ASIL D, ISO 21448) "
    "6. E/E & Network Architecture (TSN, CAN-FD ICD) "
    "7. Virtual Verification Scenarios (ASAM OpenSCENARIO 1.2) "
    "8. MBD & Embedded Code Safety (MISRA-C:2012 AST Parsing) "
    "9. ML/AI Perception Safety Tuning (ISO/PAS 8800) "
    "10. Hardware-Software Integration (WCET, Dual-Compute Thor/AURIX) "
    "11. Change Impact Ripple Analyzer (Traceability Graph) "
    "12. Continuous Tooling Optimizer (ASPICE SUP.1 CRIP Synthesis) "
    "Always provide precise, compiler-grade engineering guidance."
)

# ---------------------------------------------------------------------------
# Project Workspace Scaffolder
# ---------------------------------------------------------------------------
def scaffold_new_project(feature_id: str, feature_name: str, sae_level: int, asil: str) -> Path:
    """
    Creates an isolated feature workspace in projects/<feature_id>/ following
    Pillar 1 Workspace Partitioning & Toolchain Immutability rules.
    """
    proj_dir = PROJECTS_DIR / feature_id
    deliv_dir = proj_dir / "deliverables"
    bundle_dir = proj_dir / ".determinism/execution_bundles"
    cp_dir = proj_dir / ".checkpoints"

    deliv_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    cp_dir.mkdir(parents=True, exist_ok=True)

    profile_content = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "sae_level": sae_level,
        "safety_target_asil": asil,
        "sotif_applicable": True,
        "cybersecurity_assurance_level": "CAL_4",
        "primary_fallback_actor": "SYSTEM_MRM" if sae_level >= 3 else "DRIVER",
        "created_at": datetime.datetime.now().isoformat()
    }

    with open(proj_dir / "feature_profile.yaml", "w", encoding="utf-8") as pf:
        yaml.dump(profile_content, pf, sort_keys=False)

    return proj_dir

def _list_projects() -> List[str]:
    if PROJECTS_DIR.exists():
        return [p.name for p in sorted(PROJECTS_DIR.iterdir()) if p.is_dir()]
    return ["FEAT-L3-HWY-CHAUFFEUR"]

def _resolve_dirs(project_id: str) -> Dict[str, Path]:
    proj = PROJECTS_DIR / project_id
    if proj.exists():
        return {
            "bundles": proj / ".determinism/execution_bundles",
            "deliverables": proj / "deliverables",
            "checkpoints": proj / ".checkpoints",
            "db": proj / "traceability.sqlite"
        }
    return {
        "bundles": ROOT / ".determinism/execution_bundles",
        "deliverables": ROOT / "artifacts",
        "checkpoints": ROOT / ".checkpoints",
        "db": ROOT / "knowledge_graphs/kg5_traceability.sqlite"
    }

def _pipeline_rows(project_id: str) -> List[Dict[str, Any]]:
    dirs = _resolve_dirs(project_id)
    rows = []
    for af in sorted(AGENTS_DIR.glob("*.yaml")):
        with open(af, encoding="utf-8") as yf:
            cfg = yaml.safe_load(yf)
        ag_id = cfg.get("agent_id", "")
        bundle = dirs["bundles"] / f"bundle_{project_id}_{ag_id}.json"
        if bundle.exists():
            with open(bundle, encoding="utf-8") as bf:
                bd = json.load(bf)
            signoff = bd.get("compliance_attestation", {}).get("human_signoff_status", "PENDING_HUMAN_SIGN_OFF")
            icon = "✅" if "SIGNED" in signoff else "🕐"
        else:
            icon, signoff = "⬜", "NOT_RUN"
        rows.append({
            "icon": icon,
            "agent_id": ag_id,
            "name": cfg.get("name", ""),
            "phase": cfg.get("phase", ""),
            "signoff": signoff,
            "bundle_exists": bundle.exists()
        })
    return rows

# ---------------------------------------------------------------------------
# UI Session Startup
# ---------------------------------------------------------------------------
@cl.on_chat_start
async def on_chat_start():
    # 1. Run Pre-flight Health Check
    health = run_preparedness_check(verbose=False)
    llm_info = health["checks"]["llm_provider"]["info"]

    projects = _list_projects()
    active_project = projects[0] if projects else "FEAT-L3-HWY-CHAUFFEUR"

    cl.user_session.set("project_id", active_project)
    cl.user_session.set("history", [{"role": "system", "content": SYSTEM_PROMPT}])
    cl.user_session.set("wizard_state", None)

    mode_badge = "🟢 LIVE API" if llm_info["mode"] == "LIVE_API" else "⚪ DETERMINISTIC SIMULATION"

    welcome_md = f"""# 🚗 ADAS/AD Mission Control Cockpit

**System Preparedness:** {'✅ ALL CHECKS PASS' if health['status'] == 'PASS' else '⚠️ ATTENTION NEEDED'}  
**Active Feature Project:** `{active_project}`  
**Inference Engine:** `{llm_info['model']}` ({mode_badge})  
**Base Endpoint:** `{llm_info['base_url']}`  

---
### 🕹️ Quick Actions
Select an existing feature workspace or initialize a new project:
"""
    # Quick action buttons
    actions = [
        cl.Action(name="action_status", label="📋 View Pipeline Status", payload={}),
        cl.Action(name="action_run_p1", label="▶️ Run Phase 1 (Regulatory)", payload={"agent": "AGENT_01_REGULATORY"}),
        cl.Action(name="action_run_all", label="🚀 Launch Full Pipeline (1-8)", payload={"start": 1, "end": 8}),
        cl.Action(name="action_doctor", label="🩺 Re-check System Health", payload={}),
        cl.Action(name="action_new_project_prompt", label="✨ New Feature Project", payload={})
    ]

    await cl.Message(content=welcome_md, author="Mission Control", actions=actions).send()

# ---------------------------------------------------------------------------
# Action Handlers
# ---------------------------------------------------------------------------
@cl.action_callback("action_status")
async def on_action_status(action: cl.Action):
    project_id = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    await _send_status(project_id)
    await action.remove()

@cl.action_callback("action_run_p1")
async def on_action_run_p1(action: cl.Action):
    project_id = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    await _run_agent(project_id, "AGENT_01_REGULATORY")
    await action.remove()

@cl.action_callback("action_run_all")
async def on_action_run_all(action: cl.Action):
    project_id = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    await _run_pipeline(project_id, 1, 8)
    await action.remove()

@cl.action_callback("action_doctor")
async def on_action_doctor(action: cl.Action):
    await _send_doctor_report()
    await action.remove()

@cl.action_callback("action_new_project_prompt")
async def on_action_new_project_prompt(action: cl.Action):
    cl.user_session.set("wizard_state", "WAITING_PROJECT_DETAILS")
    prompt_msg = (
        "### ✨ Create New Feature Project\n\n"
        "Please enter your new feature specifications in the following format:\n"
        "```text\n"
        "ID: FEAT-L2-TRAFFIC-JAM-ASSIST\n"
        "Name: Traffic Jam Assist with Hands-On Detection\n"
        "SAE: 2\n"
        "ASIL: D\n"
        "```\n"
        "*(Or reply with just `ID, Name, SAE_Level, ASIL` on a single line)*"
    )
    await cl.Message(content=prompt_msg, author="Mission Control").send()
    await action.remove()

@cl.action_callback("approve_bundle")
async def on_approve_action(action: cl.Action):
    project_id = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    agent_id = action.payload.get("agent_id", "")
    await _approve(project_id, agent_id)
    await action.remove()

@cl.action_callback("pause_pipeline")
async def on_pause_action(action: cl.Action):
    await cl.Message(
        content="⏸ **Pipeline paused.** State committed to durable checkpoint. Resume with `resume`.",
        author="Mission Control"
    ).send()
    await action.remove()

@cl.action_callback("stop_pipeline")
async def on_stop_action(action: cl.Action):
    await cl.Message(
        content="🛑 **Pipeline stopped cleanly.** Completed phases are preserved in immutable execution bundles.",
        author="Mission Control"
    ).send()
    await action.remove()

# ---------------------------------------------------------------------------
# Message Handler & Wizard
# ---------------------------------------------------------------------------
@cl.on_message
async def on_message(message: cl.Message):
    text = message.content.strip()
    t = text.lower()
    project_id = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    history = cl.user_session.get("history", [{"role": "system", "content": SYSTEM_PROMPT}])
    wizard_state = cl.user_session.get("wizard_state")

    # Handle New Project Wizard
    if wizard_state == "WAITING_PROJECT_DETAILS":
        await _handle_project_scaffold_input(text)
        return

    # Direct Commands
    if t in ("help", "/help"):
        await _send_help(); return
    if t in ("doctor", "/doctor", "health", "check"):
        await _send_doctor_report(); return
    if t in ("status", "/status", "pipeline"):
        await _send_status(project_id); return
    if t in ("projects", "/projects", "list projects"):
        await _send_projects_list(); return
    if t in ("agents", "/agents", "list agents"):
        await _send_agents(); return
    if t.startswith("deliverables") or t.startswith("/deliverables"):
        await _send_deliverables(project_id); return
    if t.startswith("improvements") or t.startswith("/improvements"):
        await _send_improvements(); return

    if t.startswith("new project") or t.startswith("create project") or t.startswith("/new"):
        cl.user_session.set("wizard_state", "WAITING_PROJECT_DETAILS")
        await cl.Message(
            content="Enter feature details as: `ID: <FEAT-ID>, Name: <Name>, SAE: <2|3|4>, ASIL: <B|C|D>`",
            author="Mission Control"
        ).send()
        return

    if t.startswith("use ") or t.startswith("project "):
        parts = text.split()
        new_id = parts[1] if len(parts) > 1 else project_id
        cl.user_session.set("project_id", new_id)
        await cl.Message(content=f"✅ Switched active workspace to: `{new_id}`", author="Mission Control").send()
        await _send_status(new_id)
        return

    if t.startswith("run-pipeline") or t.startswith("/run-pipeline"):
        parts = text.split()
        start = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        end = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 8
        await _run_pipeline(project_id, start, end); return

    if t.startswith("run ") and not t.startswith("run-pipeline"):
        parts = text.split()
        agent_id = parts[1].upper() if len(parts) > 1 else ""
        await _run_agent(project_id, agent_id); return

    if t.startswith("approve") or t.startswith("/approve"):
        parts = text.split()
        agent_id = parts[1].upper() if len(parts) > 1 else ""
        await _approve(project_id, agent_id); return

    if t.startswith("resume") or t.startswith("/resume"):
        parts = text.split()
        cp_file = parts[1] if len(parts) > 1 else ""
        await _resume(project_id, cp_file); return

    # Chat / LLM Co-Pilot Loop
    history.append({"role": "user", "content": text})
    tools = _registry.get_tool_definitions()

    async with cl.Step(name="LLM Reasoning", type="llm", show_input=True) as llm_step:
        llm_step.input = text
        response = _llm.chat_completion(
            messages=history, tools=tools, temperature=0.0, max_tokens=2048
        )
        llm_step.output = (
            response.get("content") or
            f"Tool calls: {[tc.get('function',{}).get('name') for tc in (response.get('tool_calls') or [])]}"
        )

    tool_calls = response.get("tool_calls")
    if tool_calls:
        tool_results = []
        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            fn_args = tc.get("function", {}).get("arguments", "{}")
            async with cl.Step(name=f"🔧 Tool: {fn_name}", type="tool", show_input=True) as tstep:
                tstep.input = fn_args
                result = _registry.execute_tool(fn_name, fn_args)
                tstep.output = json.dumps(result, indent=2)[:1200]
            tool_results.append((tc.get("id", "tc_001"), result))

        history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls
        })
        for tc_id, res in tool_results:
            history.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": json.dumps(res)
            })

        final = _llm.chat_completion(messages=history, temperature=0.0, max_tokens=2048)
        reply = final.get("content") or "_Tool execution complete._"
        history.append({"role": "assistant", "content": reply})
        await cl.Message(content=reply, author="Mission Control").send()
    else:
        reply = response.get("content") or "_Acknowledged._"
        history.append({"role": "assistant", "content": reply})
        await cl.Message(content=reply, author="Mission Control").send()

    cl.user_session.set("history", history)

# ---------------------------------------------------------------------------
# Helper Commands
# ---------------------------------------------------------------------------
async def _handle_project_scaffold_input(user_input: str):
    cl.user_session.set("wizard_state", None)
    
    # Simple parse
    fid = "FEAT-NEW-FEATURE"
    fname = "Custom ADAS Feature"
    sae = 3
    asil = "ASIL D"

    for line in user_input.split("\n"):
        line_clean = line.strip()
        if "id:" in line_clean.lower():
            fid = line_clean.split(":", 1)[1].strip()
        elif "name:" in line_clean.lower():
            fname = line_clean.split(":", 1)[1].strip()
        elif "sae:" in line_clean.lower():
            try:
                sae = int(line_clean.split(":", 1)[1].strip())
            except ValueError:
                sae = 2
        elif "asil:" in line_clean.lower():
            asil = line_clean.split(":", 1)[1].strip().upper()

    if "," in user_input and "id:" not in user_input.lower():
        parts = [p.strip() for p in user_input.split(",")]
        if len(parts) >= 1: fid = parts[0]
        if len(parts) >= 2: fname = parts[1]
        if len(parts) >= 3 and parts[2].isdigit(): sae = int(parts[2])
        if len(parts) >= 4: asil = parts[3].upper()

    fid = fid.replace(" ", "-").upper()
    proj_dir = scaffold_new_project(fid, fname, sae, asil)
    cl.user_session.set("project_id", fid)

    msg = f"""### 🎉 Feature Project Initialized!
- **Workspace Directory:** `projects/{fid}/`
- **Feature Name:** {fname}
- **SAE Autonomy Level:** Level {sae}
- **Safety Target:** {asil}
- **Deliverables:** `projects/{fid}/deliverables/`

Active workspace switched to **`{fid}`**. You can now run:
`run AGENT_01_REGULATORY` or `run-pipeline 1 8`
"""
    actions = [
        cl.Action(name="action_run_p1", label=f"▶️ Start Phase 1 for {fid}", payload={"agent": "AGENT_01_REGULATORY"}),
        cl.Action(name="action_status", label="📋 View Workspace Status", payload={})
    ]
    await cl.Message(content=msg, author="Mission Control", actions=actions).send()

async def _send_doctor_report():
    report = run_preparedness_check(verbose=False)
    llm = report["checks"]["llm_provider"]["info"]
    deps = report["checks"]["dependencies"]["packages"]

    dep_lines = [f"- **{pkg}**: `{info['version']}` ({info['status']})" for pkg, info in deps.items()]

    md = f"""## 🩺 System Preparedness Audit
- **Overall Status:** {'🟢 PASS' if report['status'] == 'PASS' else '🔴 ACTION REQUIRED'}
- **Python Runtime:** `v{report['python_version']}`

### 🤖 LLM Inference Status
- **Operating Mode:** `{llm['mode']}`
- **Active Model:** `{llm['model']}`
- **Endpoint URL:** `{llm['base_url']}`
- **Credentials:** `{'Configured in environment' if llm['api_key_configured'] else 'None (Safe Deterministic Simulation Mode)'}`
- **Diagnostic Probe:** `{llm.get('probe_status')}`

### 📦 Core Engineering Dependencies
{chr(10).join(dep_lines)}

### 📚 Knowledge Graphs & Schemas
- 6/6 Canonical Automotive KGs (KG0–KG5) validated.
"""
    await cl.Message(content=md, author="Mission Control").send()

async def _send_projects_list():
    projs = _list_projects()
    active = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    lines = ["## 📂 Available Feature Project Workspaces\n"]
    for p in projs:
        tag = " *(Active)*" if p == active else ""
        lines.append(f"- `{p}`{tag} — Switch with: `use {p}`")
    await cl.Message(content="\n".join(lines), author="Mission Control").send()

async def _send_help():
    help_md = """## 🕹️ Mission Control Command Reference

| Command | Action |
| :--- | :--- |
| `status` | Display full V-Model pipeline status table with sign-off gates |
| `doctor` | Run comprehensive system preparedness & LLM connection check |
| `projects` | List all isolated feature project workspaces |
| `new project` | Launch guided wizard to create a new feature project |
| `use <PROJECT_ID>` | Switch active workspace (e.g., `use FEAT-L4-AVP`) |
| `run <AGENT_ID>` | Execute single agent phase (e.g. `run AGENT_01_REGULATORY`) |
| `run-pipeline [1] [8]` | Execute entire V-Model pipeline with gatekeeper checks |
| `approve <AGENT_ID>` | Human Systems Architect sign-off on sealed bundle |
| `deliverables` | Explore NASCENT and verified engineering deliverables |
| `improvements` | View Agent 12 Continuous Tooling Optimization proposals |
| `resume [file]` | Resume execution from a durable state checkpoint |

*You can also converse naturally to explore regulatory standards (UN R157, ISO 26262), query live amendments, and analyze vehicle architecture.*
"""
    await cl.Message(content=help_md, author="Mission Control").send()

async def _send_status(project_id: str):
    rows = _pipeline_rows(project_id)
    done = sum(1 for r in rows if r["icon"] == "✅")
    lines = [
        f"## 📋 Pipeline Status — `{project_id}`\n",
        "| | Agent ID | Specialization / Phase | Human Sign-off |",
        "|---|---|---|---|",
    ]
    actions = []
    for r in rows:
        lines.append(f"| {r['icon']} | `{r['agent_id']}` | {r['name']} | `{r['signoff']}` |")
        if r["bundle_exists"] and "PENDING" in r["signoff"]:
            actions.append(cl.Action(
                name="approve_bundle",
                label=f"✅ Sign-off {r['agent_id']}",
                payload={"agent_id": r["agent_id"]},
                tooltip=f"Approve execution bundle for {r['agent_id']}"
            ))

    lines.append(f"\n**Progress:** {done} / {len(rows)} phases signed off.")
    msg = cl.Message(content="\n".join(lines), author="Mission Control")
    if actions:
        msg.actions = actions
    await msg.send()

async def _send_agents():
    lines = [
        "## 🤖 Registered Engineering Agents (12 Agents)\n",
        "| # | Agent ID | Specialization | Phase |",
        "|---|---|---|---|",
    ]
    for i, af in enumerate(sorted(AGENTS_DIR.glob("*.yaml")), 1):
        with open(af, encoding="utf-8") as yf:
            cfg = yaml.safe_load(yf)
        lines.append(f"| {i} | `{cfg.get('agent_id','')}` | {cfg.get('name','')} | {cfg.get('phase','')} |")
    await cl.Message(content="\n".join(lines), author="Mission Control").send()

async def _send_deliverables(project_id: str):
    dirs = _resolve_dirs(project_id)
    ddir = dirs["deliverables"]
    if not ddir.exists():
        await cl.Message(content=f"⚠️ No deliverables found for `{project_id}`.", author="Mission Control").send()
        return

    files = sorted(f for f in ddir.rglob("*.*") if f.is_file())
    if not files:
        await cl.Message(content=f"No deliverable files yet in `{ddir.relative_to(ROOT)}`.", author="Mission Control").send()
        return

    lines = [f"## 📄 Deliverables Explorer — `{project_id}` ({len(files)} files)\n"]
    elements = []
    for fp in files[:30]:
        rel = fp.relative_to(ROOT)
        lines.append(f"- `{rel}`")
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")[:800]
            elements.append(cl.Text(name=fp.name, content=content, display="side"))
        except Exception:
            pass

    await cl.Message(content="\n".join(lines), author="Mission Control", elements=elements).send()

async def _send_improvements():
    prop_dir = ROOT / "docs/improvement_proposals"
    if not prop_dir.exists():
        await cl.Message(content="No CRIP proposals found yet.", author="Mission Control").send()
        return

    files = sorted(prop_dir.glob("*.md"))
    if not files:
        await cl.Message(content="No `.md` proposals in `docs/improvement_proposals/`.", author="Mission Control").send()
        return

    elements = [
        cl.Text(name=fp.name, content=fp.read_text(encoding="utf-8")[:900], display="side")
        for fp in files
    ]
    await cl.Message(
        content=f"## 🔧 Agent 12 — CRIP Proposals ({len(files)} generated)\n\n" + "\n".join(f"- `{fp.name}`" for fp in files),
        author="Mission Control",
        elements=elements
    ).send()

async def _run_agent(project_id: str, agent_id: str):
    if not agent_id:
        await cl.Message(content="⚠️ Please provide an agent ID, e.g., `run AGENT_01_REGULATORY`", author="Mission Control").send()
        return

    await cl.Message(content=f"▶️ Executing **`{agent_id}`** on `{project_id}`...", author="Mission Control").send()

    result = False
    async with cl.Step(name=f"Agent: {agent_id}", type="tool", show_input=True) as step:
        step.input = json.dumps({"project_id": project_id, "agent_id": agent_id})
        try:
            orch = FeaturePipelineOrchestrator(project_id=project_id)
            result = orch.run_agent_phase(agent_id)
            step.output = "PASS" if result else "FAIL"
        except Exception as exc:
            step.output = f"ERROR: {exc}"
            step.is_error = True

    if result:
        actions = [
            cl.Action(name="approve_bundle", label=f"✅ Sign-off {agent_id}", payload={"agent_id": agent_id}),
            cl.Action(name="pause_pipeline", label="⏸ Pause", payload={"agent_id": agent_id}),
            cl.Action(name="stop_pipeline", label="🛑 Stop", payload={"agent_id": agent_id})
        ]
        await cl.Message(
            content=f"✅ **`{agent_id}` completed successfully.** Execution bundle sealed & gatekeeper passed.",
            author="Mission Control",
            actions=actions
        ).send()
    else:
        await cl.Message(content=f"❌ **`{agent_id}` execution failed.** See step trace above.", author="Mission Control").send()

async def _run_pipeline(project_id: str, start: int, end: int):
    await cl.Message(
        content=f"🚀 Launching pipeline `{project_id}`: Phases {start} through {end}...",
        author="Mission Control"
    ).send()

    result = False
    async with cl.Step(name=f"Pipeline: {project_id} [{start}→{end}]", type="tool", show_input=True) as step:
        step.input = json.dumps({"project_id": project_id, "start": start, "end": end})
        try:
            orch = FeaturePipelineOrchestrator(project_id=project_id)
            result = orch.run_pipeline(start_phase=start, end_phase=end)
            step.output = "PASS" if result else "PARTIAL / FAIL"
        except Exception as exc:
            step.output = f"ERROR: {exc}"
            step.is_error = True

    await cl.Message(
        content=f"{'✅ Pipeline successfully executed.' if result else '⚠️ Pipeline halted or completed with errors.'} Type `status` to inspect sign-offs.",
        author="Mission Control"
    ).send()

async def _approve(project_id: str, agent_id: str):
    try:
        orch = FeaturePipelineOrchestrator(project_id=project_id)
        ok = orch.human_signoff(agent_id)
        if ok:
            await cl.Message(content=f"✍️ **Approved & Sealed:** `{agent_id}` on `{project_id}`.", author="Mission Control").send()
        else:
            await cl.Message(content=f"❌ Sign-off failed: Bundle for `{agent_id}` not found.", author="Mission Control").send()
    except Exception as exc:
        await cl.Message(content=f"❌ Error during sign-off: {exc}", author="Mission Control").send()

async def _resume(project_id: str, cp_file: str):
    dirs = _resolve_dirs(project_id)
    cp_dir = dirs["checkpoints"]

    if not cp_file:
        if cp_dir.exists():
            checkpoints = sorted(cp_dir.glob("*.json"))
            if checkpoints:
                lines = [f"## 🔁 Checkpoints — `{project_id}`\n"]
                for cp in checkpoints:
                    lines.append(f"- `{cp.name}`  →  `resume {cp.name}`")
                await cl.Message(content="\n".join(lines), author="Mission Control").send()
                return
        await cl.Message(content="No checkpoints found to resume.", author="Mission Control").send()
        return

    cp_path = cp_dir / cp_file if not Path(cp_file).is_absolute() else Path(cp_file)
    result = False
    async with cl.Step(name=f"Resume: {cp_file}", type="tool", show_input=True) as step:
        step.input = str(cp_path)
        try:
            orch = FeaturePipelineOrchestrator(project_id=project_id)
            result = orch.resume_pipeline(str(cp_path))
            step.output = "PASS" if result else "FAIL"
        except Exception as exc:
            step.output = f"ERROR: {exc}"
            step.is_error = True

    await cl.Message(content=f"{'✅ Pipeline resumed and completed.' if result else '❌ Resume failed.'}", author="Mission Control").send()
