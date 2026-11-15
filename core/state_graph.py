"""
Core Module: LangGraph-Inspired State Machine, Durable Checkpointer & Hierarchical Tracer
Provides:
  1. AutomotiveFeatureState: Typed, auditable state representation for ASPICE V-Model workflows.
  2. DurableCheckpointer: Time-travel, rewind, state persistence, and patch-on-resume.
  3. HierarchicalTracer: LangSmith-style nested execution traces, token/latency logging, and feedback.
  4. StateGraphEngine: Human-in-the-Loop orchestration with step-mode, breakpoints, and graceful SIGINT pause.
"""

import os
import sys
import json
import time
import signal
import uuid
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

# Add project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core.runtime import DeterministicAgentRuntime, ToolchainImmutabilityViolationError
from core.agent_executor import AgentReActExecutor
from validators.pre_review_gatekeeper import run_gatekeeper

PIPELINE_SEQUENCE = [
    {"phase": 1, "agent_id": "AGENT_01_REGULATORY", "name": "Regulatory & Legal Homologation"},
    {"phase": 2, "agent_id": "AGENT_02_ODD_ARCHITECT", "name": "ODD Definition & Formalization"},
    {"phase": 3, "agent_id": "AGENT_03_FEATURE_ACTIVATION", "name": "Connected Services & Cybersecurity"},
    {"phase": 4, "agent_id": "AGENT_04_HUMAN_FACTORS_HMI", "name": "HMI, DMS & Transition of Control"},
    {"phase": 5, "agent_id": "AGENT_05_SAFETY_SOTIF_AI", "name": "Unified Safety (HARA, SOTIF, AI)"},
    {"phase": 6, "agent_id": "AGENT_06_SYSTEM_EE_ARCH", "name": "E/E Architecture, TSN & CAN-FD ICD"},
    {"phase": 7, "agent_id": "AGENT_07_SCENARIO_SIM_ORCH", "name": "Scenario Generation & Simulation"},
    {"phase": 8, "agent_id": "AGENT_08_MBD_VERIFICATION", "name": "MBD Embedded C Code & SiL"}
]

class HierarchicalTracer:
    """LangSmith-style hierarchical execution and feedback tracer."""
    def __init__(self):
        self.traces: List[Dict[str, Any]] = []

    def start_span(
        self,
        name: str,
        run_type: str, # "FEATURE", "PHASE", "AGENT", "TOOL", "GATEKEEPER"
        inputs: Dict[str, Any],
        parent_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        run_id = str(uuid.uuid4())[:8]
        span = {
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "name": name,
            "run_type": run_type,
            "start_time": datetime.now(timezone.utc).isoformat(),
            "inputs": inputs,
            "metadata": metadata or {},
            "status": "RUNNING",
            "outputs": None,
            "error": None,
            "duration_ms": 0.0,
            "feedback": []
        }
        self.traces.append(span)
        return run_id

    def end_span(
        self,
        run_id: str,
        outputs: Optional[Dict[str, Any]] = None,
        status: str = "COMPLETED",
        error: Optional[str] = None
    ):
        for span in self.traces:
            if span["run_id"] == run_id:
                span["status"] = status
                span["outputs"] = outputs
                span["error"] = error
                start_dt = datetime.fromisoformat(span["start_time"])
                now_dt = datetime.now(timezone.utc)
                span["duration_ms"] = round((now_dt - start_dt).total_seconds() * 1000, 2)
                span["end_time"] = now_dt.isoformat()
                break

    def add_feedback(
        self,
        run_id: str,
        reviewer: str,
        verdict: str, # "APPROVED", "REJECTED", "CORRECTION_REQUESTED"
        comments: str,
        tags: Optional[List[str]] = None
    ):
        for span in self.traces:
            if span["run_id"] == run_id or run_id == "LATEST":
                span.setdefault("feedback", []).append({
                    "feedback_id": str(uuid.uuid4())[:6],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reviewer": reviewer,
                    "verdict": verdict,
                    "comments": comments,
                    "tags": tags or []
                })
                break

    def render_tree(self) -> str:
        """Renders an ASCII hierarchical tree representation of runs."""
        lines = ["\n=== LangSmith-Style Hierarchical Trace Tree ==="]
        for span in self.traces:
            indent = "  " if span.get("parent_run_id") else ""
            status_symbol = "[OK]" if span["status"] == "COMPLETED" else f"[{span['status']}]"
            lines.append(
                f"{indent}|-- {status_symbol} {span['name']} ({span['run_type']}) "
                f"[ID:{span['run_id']}] - {span['duration_ms']}ms"
            )
            if span.get("error"):
                lines.append(f"{indent}    |-- ERROR: {span['error']}")
            for fb in span.get("feedback", []):
                lines.append(f"{indent}    |-- FEEDBACK ({fb['verdict']}) by {fb['reviewer']}: {fb['comments']}")
        lines.append("================================================\n")
        return "\n".join(lines)


class DurableCheckpointer:
    """LangGraph-style durable state persistence and time-travel rewind engine."""
    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: Dict[str, Any], tag: Optional[str] = None) -> Path:
        feature_id = state.get("feature_id", "FEAT_DEFAULT")
        agent_id = state.get("current_agent", "AGENT_INIT")
        phase = state.get("current_phase", 0)
        
        # Calculate state hash for tamper detection
        serialized = json.dumps(state, sort_keys=True)
        state_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
        state["checkpoint_id"] = state_hash
        state["saved_at"] = datetime.now(timezone.utc).isoformat()

        tag_suffix = f"_{tag}" if tag else ""
        filename = f"checkpoint_{feature_id}_phase{phase}_{agent_id}{tag_suffix}.json"
        target_path = self.checkpoint_dir / filename

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        # Also maintain checkpoint_latest.json
        latest_path = self.checkpoint_dir / f"checkpoint_{feature_id}_latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        return target_path

    def load(self, checkpoint_path: Path) -> Dict[str, Any]:
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_checkpoints(self, feature_id: Optional[str] = None) -> List[Path]:
        pattern = f"checkpoint_{feature_id}*.json" if feature_id else "checkpoint_*.json"
        return sorted(self.checkpoint_dir.glob(pattern), key=os.path.getmtime)


class StateGraphEngine:
    """
    StateGraph Orchestrator implementing:
    - Step-by-step interactive mode (--step)
    - Breakpoints (--pause-after)
    - Resume from checkpoint (--resume-from)
    - Graceful SIGINT (Ctrl+C) handling
    - Full LangSmith tracing
    """
    def __init__(
        self,
        feature_id: str,
        project_dir: Optional[Path] = None,
        base_dir: Optional[Path] = None,
        step_mode: bool = False,
        pause_after: Optional[List[str]] = None
    ):
        self.feature_id = feature_id
        self.base_dir = base_dir or ROOT
        self.project_dir = project_dir or (self.base_dir / f"projects/{feature_id}")
        self.runtime = DeterministicAgentRuntime(base_dir=str(self.base_dir), project_id=feature_id)
        
        self.checkpointer = DurableCheckpointer(self.runtime.checkpoint_dir)
        self.tracer = HierarchicalTracer()
        self.step_mode = step_mode
        self.pause_after = set(pause_after or [])
        
        self.interrupted = False
        self._setup_signal_handlers()

        # Load or initialize state
        latest_cp = self.runtime.checkpoint_dir / f"checkpoint_{feature_id}_latest.json"
        if latest_cp.exists():
            self.state = self.checkpointer.load(latest_cp)
        else:
            self.state = self._init_initial_state()

    def _setup_signal_handlers(self):
        """Captures SIGINT (Ctrl+C) to prevent corrupting state or in-flight files."""
        def handle_sigint(signum, frame):
            print("\n\n[INTERRUPT DETECTED] Gracefully pausing pipeline at safe boundary...")
            self.interrupted = True
            self.state["status"] = "INTERRUPTED"
            saved_p = self.checkpointer.save(self.state, tag="INTERRUPTED")
            print(f"[STATE PRESERVED] Safe checkpoint committed: {saved_p.name}")
            print("You can resume anytime with: python orchestrator/pipeline_runner.py --resume-from", str(saved_p))
            sys.exit(130)

        try:
            signal.signal(signal.SIGINT, handle_sigint)
        except (ValueError, AttributeError):
            # On non-main thread or unsupported OS thread
            pass

    def _init_initial_state(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "current_phase": 0,
            "current_agent": None,
            "status": "INITIALIZED",
            "deliverables": {},
            "gatekeeper_verdicts": {},
            "completed_phases": [],
            "checkpoint_id": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def resume_from_checkpoint(self, checkpoint_path: Path, patch_data: Optional[Dict[str, Any]] = None):
        """Restores state from an exact checkpoint and optionally applies parameter patches."""
        self.state = self.checkpointer.load(checkpoint_path)
        if patch_data:
            self.state.update(patch_data)
            print(f"[PATCH APPLIED] In-flight parameters updated from user patch.")
        self.state["status"] = "RESUMED"
        print(f"[STATE RESTORED] Resumed {self.feature_id} at Phase {self.state.get('current_phase')} ({self.state.get('current_agent')})")

    def execute_node(self, node_info: Dict[str, Any]) -> bool:
        """Executes a single agent node within the LangGraph pipeline."""
        phase = node_info["phase"]
        agent_id = node_info["agent_id"]
        agent_name = node_info["name"]

        self.state["current_phase"] = phase
        self.state["current_agent"] = agent_id
        self.state["status"] = "RUNNING"

        print(f"\n=======================================================")
        print(f" >>> [PHASE {phase}] {agent_name} ({agent_id})")
        print(f"=======================================================")

        root_span = self.tracer.start_span(
            name=f"Phase_{phase}_{agent_id}",
            run_type="AGENT",
            inputs={"feature_id": self.feature_id, "phase": phase},
            metadata={"agent_id": agent_id}
        )

        try:
            # 1. Run Agent ReAct PDCA Execution
            executor = AgentReActExecutor(agent_id, base_dir=str(self.base_dir), project_id=self.feature_id)
            
            # Load feature profile
            profile_path = self.project_dir / "feature_profile.yaml"
            if not profile_path.exists():
                profile_path = self.base_dir / "profiles/feature_profile.yaml"
            
            import yaml
            with open(profile_path, "r", encoding="utf-8") as pf:
                profile_data = yaml.safe_load(pf)

            exec_res = executor.run_pdca_cycle(self.feature_id, profile_data)
            
            # 2. Process Result
            if exec_res.get("status") == "PASS":
                self.state["gatekeeper_verdicts"][agent_id] = exec_res.get("gatekeeper_verdict")
                self.state["deliverables"][agent_id] = exec_res.get("primary_output")
                if phase not in self.state["completed_phases"]:
                    self.state["completed_phases"].append(phase)

                self.tracer.end_span(root_span, outputs=exec_res, status="COMPLETED")
                
                # Checkpoint successful node
                cp_path = self.checkpointer.save(self.state)
                print(f" [CHECKPOINT SEALED] {cp_path.name}")
                print(f" [STATUS] Phase {phase} passed 100% gatekeeper verification.")
                return True
            else:
                err_msg = exec_res.get("error", "Gatekeeper rejection")
                self.tracer.end_span(root_span, outputs=exec_res, status="FAILED", error=str(err_msg))
                self.state["status"] = "GATEKEEPER_REJECT"
                self.checkpointer.save(self.state, tag="REJECTED")
                print(f" [GATEKEEPER REJECT] {err_msg}")
                return False

        except ToolchainImmutabilityViolationError as e:
            print(f" [SECURITY ABORT] {str(e)}")
            self.tracer.end_span(root_span, status="SECURITY_VIOLATION", error=str(e))
            self.state["status"] = "TOOLCHAIN_VIOLATION"
            self.checkpointer.save(self.state, tag="IMMUTABILITY_BREACH")
            raise e
        except Exception as e:
            self.tracer.end_span(root_span, status="ERROR", error=str(e))
            self.state["status"] = "ERROR"
            self.checkpointer.save(self.state, tag="ERROR")
            print(f" [EXECUTION ERROR] {str(e)}")
            return False

    def run_pipeline(self, start_phase: int = 1, end_phase: int = 8) -> bool:
        """Executes the pipeline with breakpoint checks and step-by-step interactive mode."""
        for node in PIPELINE_SEQUENCE:
            phase = node["phase"]
            agent_id = node["agent_id"]

            if phase < start_phase:
                continue
            if phase > end_phase:
                break

            # Step-mode: Interactive prompt BEFORE node execution
            if self.step_mode:
                prompt_text = (
                    f"\n[INTERACTIVE STEP] Ready to execute Phase {phase}: {node['name']} ({agent_id})\n"
                    f"Options: [Enter] Proceed | [p] Pause & Save Checkpoint | [q] Abort: "
                )
                choice = input(prompt_text).strip().lower()
                if choice == "p":
                    self.state["status"] = "PAUSED_BY_USER"
                    saved_cp = self.checkpointer.save(self.state, tag="PAUSED")
                    print(f"[PAUSED] Execution checkpoint saved: {saved_cp.name}")
                    return True
                elif choice == "q":
                    print("[ABORTED] Pipeline aborted by user.")
                    return False

            success = self.execute_node(node)
            if not success:
                print(f"\n[PIPELINE HALTED] Phase {phase} failed. Pipeline paused for correction.")
                return False

            # Breakpoint Check: Pause after specified agents
            if agent_id in self.pause_after or f"phase_{phase}" in self.pause_after:
                self.state["status"] = "BREAKPOINT_PAUSED"
                saved_cp = self.checkpointer.save(self.state, tag="BREAKPOINT")
                print(f"\n[BREAKPOINT HIT] Automatic pause after {agent_id}.")
                print(f"[CHECKPOINT] State persisted at: {saved_cp.name}")
                print(f"Resume with: python orchestrator/pipeline_runner.py --resume-from {saved_cp}\n")
                return True

        self.state["status"] = "COMPLETED"
        final_cp = self.checkpointer.save(self.state, tag="FINAL")
        print(f"\n[PIPELINE COMPLETE] All requested phases successfully executed.")
        print(f"[FINAL CHECKPOINT] {final_cp.name}")
        return True
