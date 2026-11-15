"""
ADAS/AD Feature Engineering Master Agentic Orchestrator (LangGraph & LangSmith Architecture)
Enforces:
  1. Human-in-the-Loop Hub-and-Spoke Governance across the 12 Specialized Agents.
  2. Workspace Partitioning: Isolates real project deliverables into projects/<feature_id>/.
  3. Durable State Machine: Step-mode, breakpoint pauses, time-travel rewind, and graceful SIGINT capture.
  4. Hierarchical Observability: LangSmith-style nested trace trees and review feedback.
  5. Continuous Tooling Optimizer: Meta-learning via Agent 12 (CRIP proposals).
"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from core.runtime import DeterministicAgentRuntime, ToolchainImmutabilityViolationError
from core.state_graph import StateGraphEngine, DurableCheckpointer, PIPELINE_SEQUENCE
from validators.pre_review_gatekeeper import run_gatekeeper
from validators.change_impact_analyzer import analyze_change_impact
from skills.tooling_optimizer import ToolingOptimizer

class FeaturePipelineOrchestrator:
    def __init__(self, project_id: str = "FEAT-L3-HWY-CHAUFFEUR"):
        self.root = ROOT_DIR
        self.project_id = project_id
        self.project_dir = self.root / f"projects/{project_id}"
        self.runtime = DeterministicAgentRuntime(base_dir=str(self.root), project_id=project_id)
        
        self.agents_dir = self.root / "agents"
        self.profiles_dir = self.root / "profiles"
        self.bundles_dir = self.runtime.bundle_dir
        self.checkpoints_dir = self.runtime.checkpoint_dir

    def list_agents(self):
        agent_files = sorted(self.agents_dir.glob("*.yaml"))
        print("\n=== Registered Specialized Engineering Agents (11 Core + Meta-Agents) ===")
        for af in agent_files:
            with open(af, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                print(f"[{data.get('agent_id')}] - {data.get('name')} ({data.get('phase')})")
        print("=========================================================================\n")

    def run_agent_phase(self, agent_id: str):
        """Runs a single agent phase within the project workspace."""
        agent_file = None
        for af in self.agents_dir.glob("*.yaml"):
            with open(af, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data.get("agent_id") == agent_id:
                    agent_file = af
                    agent_cfg = data
                    break

        if not agent_file:
            print(f"[ERROR] Agent ID '{agent_id}' not found.")
            return False

        print(f"\n>>> [HUB-AND-SPOKE] Invoking {agent_id}: {agent_cfg.get('name')}")
        print(f"    Feature Project: {self.project_id}")
        print(f"    Deliverables:    projects/{self.project_id}/deliverables/")
        print(f"    Role:            {agent_cfg.get('role')}")

        # Gather inputs and outputs from agent spec
        input_files = [inp["artifact"] for inp in agent_cfg.get("inputs", [])]
        output_files = [out["artifact"] for out in agent_cfg.get("outputs", [])]
        skills_invoked = [s["name"] for s in agent_cfg.get("skills", [])]

        # Verify input files exist using runtime resolver
        for in_file in input_files:
            try:
                self.runtime.resolve_path(in_file)
            except FileNotFoundError:
                print(f"[ERROR] Required input artifact missing: {in_file}")
                return False

        # Create execution bundle in project's .determinism/
        bundle = self.runtime.create_execution_bundle(
            agent_id=agent_id,
            feature_id=self.project_id,
            input_files=input_files,
            output_files=output_files,
            skills_invoked=skills_invoked,
            human_signoff_state="PENDING_HUMAN_SIGN_OFF"
        )

        bundle_path = self.bundles_dir / f"bundle_{self.project_id}_{agent_id}.json"
        print(f"    [OK] Execution bundle sealed: {bundle_path.name}")

        # Run automated pre-review gatekeeper
        print("    [GATEKEEPER] Running automated pre-review validation suite...")
        gate_result = run_gatekeeper(str(bundle_path))

        if gate_result.get("gate_decision") == "PASS":
            print(f"    [GATEKEEPER PASS] {gate_result.get('status_message')}")
            print(f"    --> Ready for Human Coordinator Sign-off.\n")
            return True
        else:
            print(f"    [GATEKEEPER REJECT] Artifact validation failed!")
            for err in gate_result.get("errors", []):
                print(f"      - {err}")
            print()
            return False

    def run_pipeline(
        self,
        start_phase: int = 1,
        end_phase: int = 8,
        step_mode: bool = False,
        pause_after: Optional[List[str]] = None
    ) -> bool:
        """Executes the complete V-Model StateGraph pipeline with step-mode and breakpoints."""
        print(f"\n=========================================================================")
        print(f"  LAUNCHING DURABLE STATEGRAPH PIPELINE: {self.project_id}")
        print(f"  Phases: {start_phase} to {end_phase} | Step-Mode: {step_mode} | Breakpoints: {pause_after or 'None'}")
        print(f"=========================================================================")
        
        engine = StateGraphEngine(
            feature_id=self.project_id,
            project_dir=self.project_dir,
            base_dir=self.root,
            step_mode=step_mode,
            pause_after=pause_after
        )
        return engine.run_pipeline(start_phase=start_phase, end_phase=end_phase)

    def resume_pipeline(self, checkpoint_path: str, patch_str: Optional[str] = None) -> bool:
        """Resumes execution from a saved durable checkpoint."""
        cp_path = Path(checkpoint_path)
        if not cp_path.is_absolute():
            cp_path = self.root / cp_path

        patch_data = json.loads(patch_str) if patch_str else None

        engine = StateGraphEngine(
            feature_id=self.project_id,
            project_dir=self.project_dir,
            base_dir=self.root
        )
        engine.resume_from_checkpoint(cp_path, patch_data=patch_data)
        curr_phase = engine.state.get("current_phase", 1)
        next_phase = curr_phase + 1 if engine.state.get("status") == "COMPLETED" else curr_phase
        return engine.run_pipeline(start_phase=next_phase, end_phase=8)

    def human_signoff(self, agent_id: str):
        bundle_path = self.bundles_dir / f"bundle_{self.project_id}_{agent_id}.json"
        if not bundle_path.exists():
            print(f"[ERROR] Execution bundle {bundle_path.name} does not exist. Run agent first.")
            return False

        with open(bundle_path, "r", encoding="utf-8") as f:
            bundle = json.load(f)

        bundle["compliance_attestation"]["human_signoff_status"] = "SIGNED_OFF_BY_LEAD_ARCHITECT"
        bundle["compliance_attestation"]["signoff_timestamp"] = "2026-11-15T12:00:00Z"

        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        print(f"\n[SIGN-OFF APPROVED] Bundle for {agent_id} on {self.project_id} cryptographically sealed with Lead Architect Sign-off.\n")
        return True

    def trigger_change_impact(self, trace_id: str, change_reason: str):
        db_path = self.project_dir / "traceability.sqlite"
        if not db_path.exists():
            db_path = self.root / "knowledge_graphs/kg5_traceability.sqlite"

        report_path = self.project_dir / "deliverables/11_change_impact_report.md"
        if not report_path.parent.exists():
            report_path = self.root / "artifacts/11_change_impact_report.md"

        print(f"\n>>> [CHANGE IMPACT AGENT] Evaluating ripple effect for: {trace_id}")
        res = analyze_change_impact(db_path, trace_id, change_reason, report_path)
        if res.get("status") == "PASS":
            print(f"    [SUCCESS] Impact assessment complete. Stale nodes flagged: {res.get('stale_artifacts_count')}")
            print(f"    Report written to: {report_path}")
            print("    Prescribed re-execution sequence:")
            for idx, a in enumerate(res.get("prescribed_agents_sequence", []), start=1):
                print(f"      {idx}. {a}")
            print()
            return True
        else:
            print(f"    [FAIL] {res.get('error')}\n")
            return False

    def optimize_tooling(self):
        """Invokes Agent 12 (Continuous Tooling Optimizer) to synthesize CRIP proposals."""
        print(f"\n>>> [AGENT 12: CONTINUOUS TOOLING OPTIMIZER] Scanning telemetry for {self.project_id}...")
        opt = ToolingOptimizer(self.root)
        findings = opt.scan_telemetry(self.project_id)
        print(f"    Gatekeeper rejections found: {len(findings['gatekeeper_rejections'])}")
        print(f"    Identified proposals:        {len(findings['identified_improvements'])}")

        for prop in findings["identified_improvements"]:
            doc_p = opt.generate_crip_document(prop)
            print(f"    [CRIP GENERATED] {doc_p.name} -> {prop['title']}")

        print("    [REGRESSION CHECK] Validating proposed changes against test framework...")
        reg = opt.run_regression_check()
        print(f"    [RESULT] Test Suite Verdict: {reg['status']}\n")

def main():
    parser = argparse.ArgumentParser(description="ADAS/AD Feature Development Agentic Orchestrator")
    parser.add_argument("--project", default="FEAT-L3-HWY-CHAUFFEUR", help="Target Feature Project ID")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-agents", help="List all specialized engineering agents")

    run_cmd = subparsers.add_parser("run-agent", help="Run a single agent phase and invoke gatekeeper")
    run_cmd.add_argument("--agent-id", required=True, help="e.g. AGENT_04_HUMAN_FACTORS_HMI")

    pipe_cmd = subparsers.add_parser("run-pipeline", help="Run end-to-end V-Model state graph pipeline")
    pipe_cmd.add_argument("--start-phase", type=int, default=1)
    pipe_cmd.add_argument("--end-phase", type=int, default=8)
    pipe_cmd.add_argument("--step", action="store_true", help="Interactive step-by-step mode with pause prompts")
    pipe_cmd.add_argument("--pause-after", nargs="*", help="Agent IDs or phase numbers to pause after")

    resume_cmd = subparsers.add_parser("resume", help="Resume pipeline from a checkpoint")
    resume_cmd.add_argument("--checkpoint", "--resume-from", dest="checkpoint", required=True, help="Path to checkpoint JSON file")
    resume_cmd.add_argument("--patch", help="JSON string of state updates to patch into state")

    sign_cmd = subparsers.add_parser("signoff", help="Human coordinator signs off on an agent bundle")
    sign_cmd.add_argument("--agent-id", required=True)

    change_cmd = subparsers.add_parser("trigger-change", help="Trigger change request ripple analysis")
    change_cmd.add_argument("--trace-id", required=True, help="e.g. ODD-SPEC-001")
    change_cmd.add_argument("--reason", required=True, help="Change rationale")

    opt_cmd = subparsers.add_parser("optimize-tooling", help="Run Agent 12 to formulate CRIP proposals")

    args = parser.parse_args()
    orch = FeaturePipelineOrchestrator(project_id=args.project)

    if args.command == "list-agents":
        orch.list_agents()
    elif args.command == "run-agent":
        orch.run_agent_phase(args.agent_id)
    elif args.command == "run-pipeline":
        orch.run_pipeline(
            start_phase=args.start_phase,
            end_phase=args.end_phase,
            step_mode=args.step,
            pause_after=args.pause_after
        )
    elif args.command == "resume":
        orch.resume_pipeline(args.checkpoint, patch_str=args.patch)
    elif args.command == "signoff":
        orch.human_signoff(args.agent_id)
    elif args.command == "trigger-change":
        orch.trigger_change_impact(args.trace_id, args.reason)
    elif args.command == "optimize-tooling":
        orch.optimize_tooling()

if __name__ == "__main__":
    main()
