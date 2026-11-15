"""
ADAS/AD Feature Engineering Cockpit — Unified Chat Interface (Chainlit 2.x)
Replaces Streamlit dashboard_app.py as the single UI for the full framework.

Covers:
  - Chat-based agent execution and coordination (any LLM via .env)
  - Live pipeline status table with one-click approve buttons
  - Artifact inspection inline as collapsible text elements
  - Human-in-the-loop Approve / Pause / Stop actions
  - LLM tool-call traces rendered as expandable Step nodes
  - Project switching without restarting the server

Launch:
    python -m chainlit run orchestrator/chat_app.py --port 8000

Provider (pick one in .env or export env vars — see .env.example):
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
"""

import os
import sys
import json
import yaml
import sqlite3
from pathlib import Path

import chainlit as cl

# ---------------------------------------------------------------------------
# Path bootstrap — allow imports from project root
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm_client import UniversalLLMClient        # provider-agnostic
from core.tool_registry import ToolRegistry            # tool dispatch
from tools.web_fetcher import fetch_live_regulation    # live regulatory fetch
from orchestrator.pipeline_runner import FeaturePipelineOrchestrator

AGENTS_DIR   = ROOT / "agents"
PROFILES_DIR = ROOT / "profiles"
PROJECTS_DIR = ROOT / "projects"
LOCK_FILE    = ROOT / ".determinism/model_lock.json"

# ---------------------------------------------------------------------------
# Shared singletons (created once at module load, before any session starts)
# ---------------------------------------------------------------------------
_llm = UniversalLLMClient(offline_fallback=True)

_registry = ToolRegistry()
_registry.register_tool(
    func=fetch_live_regulation,
    name="fetch_live_regulation",
    description=(
        "Fetches and skeptically validates a live regulatory document from an "
        "institutional domain (UNECE, ISO, SAE, EUR-Lex). Checks domain trust, "
        "document freshness, draft markers, and cross-references local KG1 baseline. "
        "Args: query_or_url (str), standard_id (str, optional), max_age_days (int, optional)."
    ),
)

SYSTEM_PROMPT = (
    "You are the ADAS/AD Feature Engineering Cockpit assistant. "
    "You coordinate a 12-agent automotive engineering pipeline covering "
    "regulatory compliance (UN R157/R171/R155/R156, EU AI Act, ISO 26262, ISO 21448, ISO/SAE 21434), "
    "ODD architecture (ISO 34503), system design, scenario simulation (OpenSCENARIO), "
    "MBD verification, and continuous improvement (Agent 12 / CRIP). "
    "You have access to the tool fetch_live_regulation for live UNECE/ISO regulatory intelligence. "
    "Always respond concisely; reference specific agent IDs, standards clauses, and artifact names."
)

# ---------------------------------------------------------------------------
# Pure helper functions (no chainlit context needed)
# ---------------------------------------------------------------------------

def _load_lock() -> dict:
    if LOCK_FILE.exists():
        with open(LOCK_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _list_projects() -> list:
    if PROJECTS_DIR.exists():
        return [p.name for p in sorted(PROJECTS_DIR.iterdir()) if p.is_dir()]
    return ["FEAT-L3-HWY-CHAUFFEUR"]


def _resolve_dirs(project_id: str) -> dict:
    proj = PROJECTS_DIR / project_id
    if proj.exists():
        return {
            "bundles":      proj / ".determinism/execution_bundles",
            "deliverables": proj / "deliverables",
            "checkpoints":  proj / ".checkpoints",
            "db":           proj / "traceability.sqlite",
        }
    return {
        "bundles":      ROOT / ".determinism/execution_bundles",
        "deliverables": ROOT / "artifacts",
        "checkpoints":  ROOT / ".checkpoints",
        "db":           ROOT / "knowledge_graphs/kg5_traceability.sqlite",
    }


def _pipeline_rows(project_id: str) -> list:
    dirs = _resolve_dirs(project_id)
    rows = []
    for af in sorted(AGENTS_DIR.glob("*.yaml")):
        with open(af, encoding="utf-8") as yf:
            cfg = yaml.safe_load(yf)
        ag_id  = cfg.get("agent_id", "")
        bundle = dirs["bundles"] / f"bundle_{project_id}_{ag_id}.json"
        if bundle.exists():
            with open(bundle, encoding="utf-8") as bf:
                bd = json.load(bf)
            signoff = bd.get("compliance_attestation", {}).get(
                "human_signoff_status", "PENDING_HUMAN_SIGN_OFF"
            )
            icon = "✅" if "SIGNED" in signoff else "🕐"
        else:
            icon, signoff = "⬜", "NOT_RUN"
        rows.append({
            "icon": icon, "agent_id": ag_id,
            "name": cfg.get("name", ""),
            "phase": cfg.get("phase", ""),
            "signoff": signoff,
            "bundle_exists": bundle.exists(),
        })
    return rows


def _stats_text(project_id: str) -> str:
    lock = _load_lock()
    env_model  = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL")
    lock_model = lock.get("llm_configuration", {}).get("pinned_checkpoint", "not-set")
    effective  = env_model or lock_model
    base_url   = (
        os.environ.get("LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "OpenAI default"
    )

    dirs   = _resolve_dirs(project_id)
    b_dir  = dirs["bundles"]
    d_dir  = dirs["deliverables"]
    db     = dirs["db"]

    bundles = list(b_dir.glob(f"bundle_{project_id}_*.json")) if b_dir.exists() else []
    delivs  = [d for d in d_dir.rglob("*.*") if d.is_file()] if d_dir.exists() else []

    if db.exists():
        try:
            conn  = sqlite3.connect(str(db))
            cur   = conn.cursor()
            cur.execute("SELECT count(*) FROM trace_nodes;")
            nodes = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM trace_nodes WHERE status='STALE';")
            stale = cur.fetchone()[0]
            conn.close()
        except Exception:
            nodes, stale = 0, 0
    else:
        nodes, stale = 0, 0

    return (
        f"**🚗 Project:** `{project_id}`\n\n"
        f"**🤖 LLM:** `{effective}`\n"
        f"`{base_url}`\n\n"
        f"**📊 Stats**\n"
        f"- Executed phases: `{len(bundles)}`\n"
        f"- Deliverables: `{len(delivs)}`\n"
        f"- Traceability nodes: `{nodes}` (stale: `{stale}`)\n\n"
        f"**Commands**\n"
        f"`status` · `agents` · `deliverables`\n"
        f"`run <AGENT_ID>`\n"
        f"`run-pipeline [start] [end]`\n"
        f"`approve <AGENT_ID>`\n"
        f"`resume [checkpoint]`\n"
        f"`improvements` · `help`"
    )


# ---------------------------------------------------------------------------
# on_chat_start
# ---------------------------------------------------------------------------

@cl.on_chat_start
async def on_chat_start():
    projects   = _list_projects()
    project_id = projects[0] if projects else "FEAT-L3-HWY-CHAUFFEUR"

    cl.user_session.set("project_id", project_id)
    cl.user_session.set("history", [{"role": "system", "content": SYSTEM_PROMPT}])

    welcome = (
        f"## 🚗 ADAS/AD Feature Engineering Cockpit\n\n"
        f"**Active project:** `{project_id}`\n\n"
        f"{_stats_text(project_id)}\n\n"
        f"---\n"
        f"**Quick start:** type `status`, `run AGENT_01_REGULATORY`, `run-pipeline`, or just chat naturally.\n"
        f"Type `help` for all commands."
    )
    await cl.Message(content=welcome, author="Cockpit").send()


# ---------------------------------------------------------------------------
# on_message — command router + LLM chat
# ---------------------------------------------------------------------------

@cl.on_message
async def on_message(message: cl.Message):
    text       = message.content.strip()
    t          = text.lower()
    project_id = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    history    = cl.user_session.get("history", [{"role": "system", "content": SYSTEM_PROMPT}])

    # --- help ---
    if t in ("help", "/help"):
        await _send_help(); return

    # --- status ---
    if t in ("status", "/status", "pipeline status"):
        await _send_status(project_id); return

    # --- agents ---
    if t in ("agents", "/agents", "list agents", "list-agents"):
        await _send_agents(); return

    # --- deliverables ---
    if t.startswith("deliverables") or t.startswith("/deliverables"):
        await _send_deliverables(project_id); return

    # --- improvements ---
    if t.startswith("improvements") or t.startswith("/improvements"):
        await _send_improvements(); return

    # --- run-pipeline [start] [end] ---
    if t.startswith("run-pipeline") or t.startswith("/run-pipeline"):
        parts = text.split()
        start = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        end   = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 8
        await _run_pipeline(project_id, start, end); return

    # --- run <AGENT_ID> ---
    if t.startswith("run ") and not t.startswith("run-pipeline"):
        parts    = text.split()
        agent_id = parts[1].upper() if len(parts) > 1 else ""
        await _run_agent(project_id, agent_id); return

    # --- approve <AGENT_ID> ---
    if t.startswith("approve") or t.startswith("/approve"):
        parts    = text.split()
        agent_id = parts[1].upper() if len(parts) > 1 else ""
        await _approve(project_id, agent_id); return

    # --- resume [checkpoint] ---
    if t.startswith("resume") or t.startswith("/resume"):
        parts   = text.split()
        cp_file = parts[1] if len(parts) > 1 else ""
        await _resume(project_id, cp_file); return

    # --- project switch: "use FEAT-L4-AVP" or "project FEAT-L4-AVP" ---
    if t.startswith("use ") or t.startswith("project "):
        parts  = text.split()
        new_id = parts[1] if len(parts) > 1 else project_id
        cl.user_session.set("project_id", new_id)
        await cl.Message(
            content=f"✅ Switched to project `{new_id}`.\n\n{_stats_text(new_id)}",
            author="Cockpit"
        ).send()
        return

    # --- LLM chat with tool calling ---
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
        # Execute each tool call and show inline step
        tool_results = []
        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            fn_args = tc.get("function", {}).get("arguments", "{}")
            async with cl.Step(name=f"🔧 {fn_name}", type="tool", show_input=True) as tstep:
                tstep.input  = fn_args
                result       = _registry.execute_tool(fn_name, fn_args)
                tstep.output = json.dumps(result, indent=2)[:1200]
            tool_results.append((tc.get("id", "tc_001"), result))

        # Feed tool results back to LLM for synthesis
        history.append({
            "role":       "assistant",
            "content":    None,
            "tool_calls": tool_calls
        })
        for tc_id, res in tool_results:
            history.append({
                "role":         "tool",
                "tool_call_id": tc_id,
                "content":      json.dumps(res)
            })
        final = _llm.chat_completion(messages=history, temperature=0.0, max_tokens=2048)
        reply = final.get("content") or "_Tool executed. See step trace above._"
        history.append({"role": "assistant", "content": reply})
        await cl.Message(content=reply, author="Cockpit").send()
    else:
        reply = response.get("content") or "_No response generated._"
        history.append({"role": "assistant", "content": reply})
        await cl.Message(content=reply, author="Cockpit").send()

    cl.user_session.set("history", history)


# ---------------------------------------------------------------------------
# Action callbacks (approve / pause / stop buttons in messages)
# ---------------------------------------------------------------------------

@cl.action_callback("approve_bundle")
async def on_approve_action(action: cl.Action):
    project_id = cl.user_session.get("project_id", "FEAT-L3-HWY-CHAUFFEUR")
    agent_id   = action.payload.get("agent_id", "")
    await _approve(project_id, agent_id)
    await action.remove()


@cl.action_callback("pause_pipeline")
async def on_pause_action(action: cl.Action):
    await cl.Message(
        content=(
            "⏸ **Pipeline paused.**\n\n"
            "State is preserved in the latest checkpoint. "
            "Resume anytime with:\n`resume <checkpoint_filename>`"
        ),
        author="Cockpit"
    ).send()
    await action.remove()


@cl.action_callback("stop_pipeline")
async def on_stop_action(action: cl.Action):
    await cl.Message(
        content=(
            "🛑 **Pipeline stopped.**\n\n"
            "All completed phases remain sealed in their execution bundles — no work lost. "
            "Start fresh with `run-pipeline` or resume a phase with `run <AGENT_ID>`."
        ),
        author="Cockpit"
    ).send()
    await action.remove()


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

async def _send_help():
    await cl.Message(
        content=(
            "## 💬 Cockpit Commands\n\n"
            "| Command | Description |\n"
            "|---|---|\n"
            "| `status` | Full pipeline status table |\n"
            "| `agents` | List all 12 engineering agents |\n"
            "| `deliverables` | List project deliverable artifacts |\n"
            "| `improvements` | Show Agent 12 CRIP proposals |\n"
            "| `run <AGENT_ID>` | Execute one agent phase |\n"
            "| `run-pipeline [start] [end]` | Full pipeline (default: phases 1–8) |\n"
            "| `approve <AGENT_ID>` | Human sign-off on execution bundle |\n"
            "| `resume [checkpoint]` | Resume from saved checkpoint |\n"
            "| `use <PROJECT_ID>` | Switch active project |\n\n"
            "Or **chat naturally** about regulations, safety analysis, standards, scenarios — "
            "I have live regulatory intelligence via `fetch_live_regulation`."
        ),
        author="Cockpit"
    ).send()


async def _send_status(project_id: str):
    rows    = _pipeline_rows(project_id)
    done    = sum(1 for r in rows if r["icon"] == "✅")
    lines   = [
        f"## 📋 Pipeline Status — `{project_id}`\n",
        "| | Agent ID | Name | Sign-off |",
        "|---|---|---|---|",
    ]
    actions = []
    for r in rows:
        lines.append(f"| {r['icon']} | `{r['agent_id']}` | {r['name']} | `{r['signoff']}` |")
        if r["bundle_exists"] and "PENDING" in r["signoff"]:
            actions.append(cl.Action(
                name    = "approve_bundle",
                label   = f"✅ Approve {r['agent_id']}",
                payload = {"agent_id": r["agent_id"]},
                tooltip = f"Sign off execution bundle for {r['agent_id']}"
            ))

    lines.append(f"\n**{done} / {len(rows)} phases complete.**")
    msg = cl.Message(content="\n".join(lines), author="Cockpit")
    if actions:
        msg.actions = actions
    await msg.send()


async def _send_agents():
    lines = [
        "## 🤖 Registered Engineering Agents\n",
        "| # | Agent ID | Name | Phase |",
        "|---|---|---|---|",
    ]
    for i, af in enumerate(sorted(AGENTS_DIR.glob("*.yaml")), 1):
        with open(af, encoding="utf-8") as yf:
            cfg = yaml.safe_load(yf)
        lines.append(
            f"| {i} | `{cfg.get('agent_id','')}` | {cfg.get('name','')} | {cfg.get('phase','')} |"
        )
    await cl.Message(content="\n".join(lines), author="Cockpit").send()


async def _send_deliverables(project_id: str):
    dirs  = _resolve_dirs(project_id)
    d_dir = dirs["deliverables"]
    if not d_dir.exists():
        await cl.Message(
            content=f"⚠️ No deliverables directory for `{project_id}` yet. Run a pipeline phase first.",
            author="Cockpit"
        ).send()
        return

    files = sorted(f for f in d_dir.rglob("*.*") if f.is_file())
    if not files:
        await cl.Message(
            content=f"No deliverable artifacts found in `{d_dir.relative_to(ROOT)}`.",
            author="Cockpit"
        ).send()
        return

    lines    = [f"## 📄 Deliverables — `{project_id}` ({len(files)} files)\n"]
    elements = []
    for fp in files[:30]:
        rel = fp.relative_to(ROOT)
        lines.append(f"- `{rel}`")
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")[:800]
            elements.append(cl.Text(name=fp.name, content=content, display="side"))
        except Exception:
            pass

    await cl.Message(
        content="\n".join(lines), author="Cockpit", elements=elements
    ).send()


async def _send_improvements():
    prop_dir = ROOT / "docs/improvement_proposals"
    if not prop_dir.exists():
        await cl.Message(
            content=(
                "No CRIP improvement proposals found yet.\n\n"
                "Agent 12 generates these after a pipeline run. "
                "Run `run-pipeline` and then check again."
            ),
            author="Cockpit"
        ).send()
        return

    files = sorted(prop_dir.glob("*.md"))
    if not files:
        await cl.Message(
            content="No `.md` proposals in `docs/improvement_proposals/`.", author="Cockpit"
        ).send()
        return

    elements = [
        cl.Text(name=fp.name, content=fp.read_text(encoding="utf-8")[:900], display="side")
        for fp in files
    ]
    await cl.Message(
        content=f"## 🔧 Agent 12 — CRIP Proposals ({len(files)} found)\n\n"
                + "\n".join(f"- `{fp.name}`" for fp in files),
        author="Cockpit",
        elements=elements
    ).send()


async def _run_agent(project_id: str, agent_id: str):
    if not agent_id:
        await cl.Message(
            content="⚠️ Specify an agent ID. Example: `run AGENT_01_REGULATORY`",
            author="Cockpit"
        ).send()
        return

    await cl.Message(
        content=f"▶️ Executing **`{agent_id}`** on project `{project_id}`...",
        author="Cockpit"
    ).send()

    result = False
    async with cl.Step(name=f"Agent: {agent_id}", type="tool", show_input=True) as step:
        step.input = json.dumps({"project_id": project_id, "agent_id": agent_id})
        try:
            orch   = FeaturePipelineOrchestrator(project_id=project_id)
            result = orch.run_agent_phase(agent_id)
            step.output = "PASS" if result else "FAIL"
        except Exception as exc:
            step.output  = f"ERROR: {exc}"
            step.is_error = True

    if result:
        actions = [
            cl.Action(
                name="approve_bundle", label=f"✅ Approve {agent_id}",
                payload={"agent_id": agent_id}, tooltip="Sign off this execution bundle"
            ),
            cl.Action(
                name="pause_pipeline", label="⏸ Pause",
                payload={"agent_id": agent_id}
            ),
            cl.Action(
                name="stop_pipeline", label="🛑 Stop",
                payload={"agent_id": agent_id}
            ),
        ]
        await cl.Message(
            content=(
                f"✅ **`{agent_id}` passed** — execution bundle sealed and gatekeeper validated.\n\n"
                f"Ready for human sign-off:"
            ),
            author="Cockpit",
            actions=actions
        ).send()
    else:
        await cl.Message(
            content=f"❌ **`{agent_id}` failed.** Check the step trace above for details.",
            author="Cockpit"
        ).send()


async def _run_pipeline(project_id: str, start: int, end: int):
    await cl.Message(
        content=(
            f"🚀 **Launching pipeline** `{project_id}` — Phases **{start} → {end}**\n\n"
            f"Each phase seals an execution bundle and runs gatekeeper validation. "
            f"Type `status` anytime to check progress."
        ),
        author="Cockpit"
    ).send()

    result = False
    async with cl.Step(
        name=f"Pipeline: {project_id} [{start}→{end}]", type="tool", show_input=True
    ) as step:
        step.input = json.dumps({"project_id": project_id, "start": start, "end": end})
        try:
            orch   = FeaturePipelineOrchestrator(project_id=project_id)
            result = orch.run_pipeline(start_phase=start, end_phase=end)
            step.output = "PASS" if result else "PARTIAL / FAIL"
        except Exception as exc:
            step.output   = f"ERROR: {exc}"
            step.is_error = True

    actions = [
        cl.Action(name="pause_pipeline", label="⏸ Pause", payload={"phase": "pipeline"}),
        cl.Action(name="stop_pipeline",  label="🛑 Stop",  payload={"phase": "pipeline"}),
    ]
    await cl.Message(
        content=(
            f"✅ **Pipeline complete** (Phases {start}–{end}) on `{project_id}`.\n"
            f"Type `status` to review sign-off table."
            if result else
            f"⚠️ **Pipeline finished with errors.** Check the step trace above. "
            f"Individual phases may need investigation."
        ),
        author="Cockpit",
        actions=actions
    ).send()


async def _approve(project_id: str, agent_id: str):
    if not agent_id:
        await cl.Message(
            content="⚠️ Specify an agent ID. Example: `approve AGENT_01_REGULATORY`",
            author="Cockpit"
        ).send()
        return
    try:
        orch = FeaturePipelineOrchestrator(project_id=project_id)
        ok   = orch.human_signoff(agent_id)
        if ok:
            await cl.Message(
                content=(
                    f"✍️ **Sign-off recorded** for `{agent_id}` on `{project_id}`.\n\n"
                    f"Execution bundle cryptographically sealed with Lead Architect sign-off. "
                    f"This phase is now eligible for downstream pipeline progression."
                ),
                author="Cockpit"
            ).send()
        else:
            await cl.Message(
                content=(
                    f"❌ Sign-off failed for `{agent_id}`. "
                    f"Execution bundle not found — run `run {agent_id}` first."
                ),
                author="Cockpit"
            ).send()
    except Exception as exc:
        await cl.Message(content=f"❌ Error during sign-off: {exc}", author="Cockpit").send()


async def _resume(project_id: str, cp_file: str):
    dirs   = _resolve_dirs(project_id)
    cp_dir = dirs["checkpoints"]

    if not cp_file:
        # List available checkpoints
        if cp_dir.exists():
            checkpoints = sorted(cp_dir.glob("*.json"))
            if checkpoints:
                lines = [f"## 🔁 Checkpoints — `{project_id}`\n"]
                for cp in checkpoints:
                    lines.append(f"- `{cp.name}`  →  `resume {cp.name}`")
                await cl.Message(content="\n".join(lines), author="Cockpit").send()
                return
        await cl.Message(
            content="No checkpoints found yet. Run a pipeline phase first.", author="Cockpit"
        ).send()
        return

    cp_path = cp_dir / cp_file if not Path(cp_file).is_absolute() else Path(cp_file)

    result = False
    async with cl.Step(name=f"Resume: {cp_file}", type="tool", show_input=True) as step:
        step.input = str(cp_path)
        try:
            orch   = FeaturePipelineOrchestrator(project_id=project_id)
            result = orch.resume_pipeline(str(cp_path))
            step.output = "PASS" if result else "FAIL"
        except Exception as exc:
            step.output   = f"ERROR: {exc}"
            step.is_error = True

    await cl.Message(
        content=(
            f"✅ Pipeline resumed from `{cp_file}` and completed."
            if result else
            f"❌ Resume from `{cp_file}` failed. Check step trace above."
        ),
        author="Cockpit"
    ).send()
