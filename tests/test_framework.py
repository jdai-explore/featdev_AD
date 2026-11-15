"""
Comprehensive Framework Verification Suite
Tests all JSON schemas, agent YAML contracts, feature profiles,
skills, determinism runtime, pre-review gatekeeper, and change ripple analysis.
"""

import sys
import json
import yaml
import unittest
import jsonschema
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core.runtime import DeterministicAgentRuntime
from skills.state_machine_verifier import verify_hmi_state_machine
from skills.bus_bandwidth_calc import evaluate_icd_performance
from skills.code_safety_linter import lint_embedded_c_code
from skills.openodd_builder import build_and_validate_openodd
from validators.pre_review_gatekeeper import run_gatekeeper
from validators.change_impact_analyzer import analyze_change_impact

class TestADASAgenticFramework(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ROOT
        cls.runtime = DeterministicAgentRuntime(base_dir=str(cls.root))

    def test_01_model_lock_configuration(self):
        """Verifies strict deterministic parameters in model_lock.json."""
        lock = self.runtime.model_lock
        self.assertEqual(lock.get("runtime_policy"), "STRICT_DETERMINISTIC")
        self.assertEqual(lock["llm_configuration"]["inference_params"]["temperature"], 0.0)
        self.assertEqual(lock["llm_configuration"]["inference_params"]["seed"], 424242)
        self.assertFalse(lock["tool_execution_policy"]["live_network_allowed"])

    def test_02_all_agent_yaml_contracts_valid(self):
        """Validates all Agent YAML contracts (11 core + meta-agents) against agent_contract.schema.json."""
        schema_path = self.root / "schemas/agent_contract.schema.json"
        with open(schema_path, "r", encoding="utf-8") as sf:
            schema = json.load(sf)

        agent_files = list((self.root / "agents").glob("*.yaml"))
        self.assertGreaterEqual(len(agent_files), 11, "Must have at least 11 agent contracts")

        for af in agent_files:
            with open(af, "r", encoding="utf-8") as yf:
                data = yaml.safe_load(yf)
                try:
                    jsonschema.validate(instance=data, schema=schema)
                except jsonschema.ValidationError as e:
                    self.fail(f"Agent contract {af.name} failed schema validation: {e.message}")

    def test_03_feature_profiles_valid(self):
        """Validates all feature profiles against feature_profile.schema.json."""
        schema_path = self.root / "schemas/feature_profile.schema.json"
        with open(schema_path, "r", encoding="utf-8") as sf:
            schema = json.load(sf)

        profile_files = list((self.root / "profiles").glob("*.yaml"))
        self.assertGreaterEqual(len(profile_files), 3)

        for pf in profile_files:
            with open(pf, "r", encoding="utf-8") as yf:
                data = yaml.safe_load(yf)
                try:
                    jsonschema.validate(instance=data, schema=schema)
                except jsonschema.ValidationError as e:
                    self.fail(f"Profile {pf.name} failed schema validation: {e.message}")

    def test_04_openodd_schema_and_lead_time_guardrails(self):
        """Verifies OpenODD YAML satisfies ASAM OpenODD schema and UN R157 >=10s lead time."""
        odd_file = self.root / "artifacts/02_lane_centering_odd.yaml"
        schema_file = self.root / "schemas/openodd.schema.json"

        with open(odd_file, "r", encoding="utf-8") as yf:
            data = yaml.safe_load(yf)

        res = build_and_validate_openodd(data, schema_file, odd_file)
        self.assertEqual(res["status"], "PASS")
        self.assertGreaterEqual(res["lead_time_s"], 10.0)

    def test_05_hmi_state_machine_formal_verification(self):
        """Mathematically verifies zero dead-ends and mandatory MRM fallback in HMI state matrix."""
        csv_file = self.root / "artifacts/04_hmi_state_matrix.csv"
        res = verify_hmi_state_machine(str(csv_file))
        self.assertEqual(res["status"], "PASS", f"HMI state machine verification failed: {res.get('errors')}")
        self.assertGreaterEqual(res["total_transitions"], 10)

    def test_06_icd_bandwidth_and_e2e_protection(self):
        """Verifies bus bandwidth and AUTOSAR E2E protection on critical signals."""
        icd_file = self.root / "artifacts/06_vehicle_arch_icd.json"
        res = evaluate_icd_performance(str(icd_file))
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["unprotected_signals"]), 0)
        self.assertEqual(len(res["wcet_issues"]), 0)

    def test_07_embedded_c_misra_and_safety_rules(self):
        """Verifies that generated C code complies with zero dynamic memory and E2E checks."""
        c_file = self.root / "artifacts/08_lane_controller.c"
        res = lint_embedded_c_code(str(c_file))
        self.assertEqual(res["status"], "PASS", f"C code safety violations: {res.get('violations')}")

    def test_08_execution_bundle_and_gatekeeper(self):
        """Verifies end-to-end execution bundle generation and automated gatekeeper decision."""
        bundle = self.runtime.create_execution_bundle(
            agent_id="AGENT_04_HUMAN_FACTORS_HMI",
            feature_id="FEAT-L3-HWY-CHAUFFEUR",
            input_files=["artifacts/01_compliance_matrix.csv", "artifacts/02_lane_centering_odd.yaml"],
            output_files=["artifacts/04_hmi_state_matrix.csv"],
            skills_invoked=["verify_hmi_state_machine"]
        )
        bundle_file = self.root / ".determinism/execution_bundles/bundle_FEAT-L3-HWY-CHAUFFEUR_AGENT_04_HUMAN_FACTORS_HMI.json"
        self.assertTrue(bundle_file.exists())

        gate_res = run_gatekeeper(str(bundle_file))
        self.assertEqual(gate_res["gate_decision"], "PASS", f"Gatekeeper rejected: {gate_res.get('errors')}")

    def test_09_change_impact_ripple_analysis(self):
        """Verifies that changing an upstream parameter flags downstream stale artifacts."""
        db_path = self.root / "knowledge_graphs/kg5_traceability.sqlite"
        report_path = self.root / "artifacts/11_change_impact_report.md"
        res = analyze_change_impact(
            db_path=db_path,
            changed_node_id="ODD-SPEC-001",
            change_reason="Lowered minimum visibility limit from 150m to 120m for highway pilot",
            output_report_path=report_path
        )
        self.assertEqual(res["status"], "PASS")
        self.assertGreater(res["stale_artifacts_count"], 0)
        self.assertTrue(report_path.exists())

    def test_10_tree_sitter_ast_misra_linter(self):
        """Verifies Tree-Sitter CST/AST parsing engine on C code safety."""
        c_file = self.root / "artifacts/08_lane_controller.c"
        res = lint_embedded_c_code(str(c_file))
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["engine"], "Tree-Sitter-C AST (C11/ISO 26262 Parser)")
        self.assertIn("LaneController_Step", res["functions_analyzed"])

    def test_11_scenariogeneration_xosc_builder(self):
        """Verifies official scenariogeneration OpenSCENARIO 1.2 XML generation."""
        params_file = self.root / "artifacts/07_scenarios/scenario_params.json"
        out_xosc = self.root / "artifacts/07_scenarios/cutin_glare.xosc"
        with open(params_file, "r", encoding="utf-8") as f:
            params = json.load(f)
        from skills.xosc_builder import generate_openscenario
        res = generate_openscenario(params, out_xosc)
        self.assertEqual(res["status"], "PASS")
        self.assertIn("scenariogeneration.xosc", res["engine"])

    def test_12_canfd_physical_protocol_framing(self):
        """Verifies ISO 11898-1:2015 CAN-FD framing and physical bit-rate overhead."""
        from skills.bus_bandwidth_calc import calculate_canfd_frame_bits
        frame = calculate_canfd_frame_bits(payload_bytes=8)
        self.assertEqual(frame["raw_payload_bits"], 64)
        self.assertGreater(frame["total_physical_bits"], 100) # Overhead + stuff bits

    def test_13_agent_react_self_correction_loop(self):
        """Verifies AgentReActExecutor PDCA cycle and automated gatekeeper sealing."""
        from core.agent_executor import AgentReActExecutor
        executor = AgentReActExecutor("AGENT_02_ODD_ARCHITECT", base_dir=str(self.root))
        profile_p = self.root / "profiles/l3_highway_chauffeur.yaml"
        with open(profile_p, "r", encoding="utf-8") as f:
            prof = yaml.safe_load(f)
        res = executor.run_pdca_cycle("FEAT-L3-HWY-CHAUFFEUR", prof)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["gatekeeper_verdict"]["gate_decision"], "PASS")

    def test_14_trace_extractor_dynamic_sync(self):
        """Verifies automated trace extraction and SQLite graph sync (Milestone 3)."""
        from skills.trace_extractor import TraceabilityExtractor
        db_file = self.root / "knowledge_graphs/kg5_traceability.sqlite"
        extractor = TraceabilityExtractor(db_file)
        targets = list((self.root / "artifacts").rglob("*.*"))
        res = extractor.extract_and_sync(targets)
        self.assertEqual(res["status"], "PASS")
        self.assertGreater(res["nodes_extracted_count"], 30)

    def test_15_regulatory_fts5_search(self):
        """Verifies SQLite FTS5 BM25 regulatory search (Milestone 3)."""
        from skills.kg_ingestor import RegulatoryKGIngestor
        ingestor = RegulatoryKGIngestor()
        ingestor.ingest_from_json()
        hits = ingestor.search_clauses("transition demand minimum risk")
        self.assertGreater(len(hits), 0)
        self.assertEqual(hits[0]["clause_id"], "UN_R157_6.1.1")

    def test_16_l4_avp_feature_stack_validation(self):
        """Verifies end-to-end L4 Automated Valet Parking feature deliverables (Milestone 5)."""
        from skills.openodd_builder import build_and_validate_openodd
        from skills.state_machine_verifier import verify_hmi_state_machine
        from skills.code_safety_linter import lint_embedded_c_code

        # 1. OpenODD
        odd_file = self.root / "artifacts/l4_avp/02_avp_odd.yaml"
        schema_file = self.root / "schemas/openodd.schema.json"
        with open(odd_file, "r", encoding="utf-8") as yf:
            odd_data = yaml.safe_load(yf)
        odd_res = build_and_validate_openodd(odd_data, schema_file, odd_file)
        self.assertEqual(odd_res["status"], "PASS")

        # 2. HMI State Machine
        hmi_file = self.root / "artifacts/l4_avp/04_avp_hmi_state_matrix.csv"
        hmi_res = verify_hmi_state_machine(str(hmi_file))
        self.assertEqual(hmi_res["status"], "PASS")

        # 3. MISRA-C AST
        c_file = self.root / "artifacts/l4_avp/08_avp_controller.c"
        c_res = lint_embedded_c_code(str(c_file))
        self.assertEqual(c_res["status"], "PASS")

    def test_17_canonical_terminology_and_kg_standards_integrity(self):
        """Verifies KG0 terminology registry and harmonized standards coverage across KG1-KG4."""
        # 1. Verify KG0 Terminology
        kg0_file = self.root / "knowledge_graphs/kg0_canonical_terminology.json"
        self.assertTrue(kg0_file.exists())
        with open(kg0_file, "r", encoding="utf-8") as f:
            kg0_data = json.load(f)
        self.assertEqual(kg0_data["graph_id"], "KG0_CANONICAL_TERMINOLOGY_REGISTRY")
        self.assertGreaterEqual(len(kg0_data["terms"]), 15)
        self.assertIn("SAE J3016:2021", kg0_data["governing_standards"])
        self.assertIn("ISO/SAE 21434:2021", kg0_data["governing_standards"])

        # 2. Verify KG1 Regulatory Standards
        kg1_file = self.root / "knowledge_graphs/kg1_regulatory.json"
        with open(kg1_file, "r", encoding="utf-8") as f:
            kg1_data = json.load(f)
        std_ids = [r["standard_id"] for r in kg1_data["regulations"]]
        self.assertIn("ISO_SAE_21434_2021", std_ids)
        self.assertIn("ISO_34503_2023", std_ids)
        self.assertIn("UL_4600_2023", std_ids)
        self.assertIn("EU_AI_ACT_2024", std_ids)

        # 3. Verify KG4 Cybersecurity Threats & SOTIF
        kg4_file = self.root / "knowledge_graphs/kg4_hazard_sotif_catalog.json"
        with open(kg4_file, "r", encoding="utf-8") as f:
            kg4_data = json.load(f)
        self.assertIn("cybersecurity_threat_scenarios", kg4_data)
        self.assertGreaterEqual(len(kg4_data["cybersecurity_threat_scenarios"]), 3)
        self.assertGreaterEqual(len(kg4_data["functional_safety_hazards"]), 5)

    def test_18_workspace_partitioning_and_immutability_guard(self):
        """Pillar 1: Verifies workspace partitioning and defense against core toolchain mutations."""
        from core.runtime import ToolchainImmutabilityViolationError
        runtime = DeterministicAgentRuntime(base_dir=str(self.root), project_id="FEAT-L3-HWY-CHAUFFEUR")
        
        # Verify deliverable and bundle paths point into projects/FEAT-L3-HWY-CHAUFFEUR/
        self.assertEqual(runtime.project_dir.name, "FEAT-L3-HWY-CHAUFFEUR")
        self.assertTrue(runtime.deliverables_dir.exists())
        self.assertTrue(runtime.bundle_dir.exists())

        # Immutability check: Attempting to write into core protected directories MUST raise error
        protected_target = self.root / "skills/malicious_patch.py"
        with self.assertRaises(ToolchainImmutabilityViolationError):
            runtime.assert_write_target_allowed(protected_target)

        # Allowed target check: Writing inside projects/FEAT-L3-HWY-CHAUFFEUR/deliverables/ must pass
        allowed_target = runtime.deliverables_dir / "02_lane_centering_odd.yaml"
        try:
            runtime.assert_write_target_allowed(allowed_target)
        except ToolchainImmutabilityViolationError:
            self.fail("Legitimate project deliverable was falsely blocked by immutability guard")

    def test_19_durable_checkpointer_and_state_graph(self):
        """Pillar 2: Verifies LangGraph-style state checkpointing, rewind, and breakpoint pausing."""
        from core.state_graph import DurableCheckpointer, StateGraphEngine
        cp_dir = self.root / "projects/FEAT-L3-HWY-CHAUFFEUR/.checkpoints"
        checkpointer = DurableCheckpointer(cp_dir)
        
        # Verify latest checkpoint exists and can be loaded
        latest_cp = cp_dir / "checkpoint_FEAT-L3-HWY-CHAUFFEUR_latest.json"
        self.assertTrue(latest_cp.exists())
        state = checkpointer.load(latest_cp)
        self.assertEqual(state["feature_id"], "FEAT-L3-HWY-CHAUFFEUR")
        self.assertIn("completed_phases", state)

        # Verify breakpoint pause engine
        engine = StateGraphEngine(
            feature_id="FEAT-L3-HWY-CHAUFFEUR",
            base_dir=self.root,
            pause_after=["AGENT_01_REGULATORY"]
        )
        res = engine.run_pipeline(start_phase=1, end_phase=3)
        self.assertTrue(res)
        self.assertEqual(engine.state["status"], "BREAKPOINT_PAUSED")
        self.assertEqual(engine.state["current_agent"], "AGENT_01_REGULATORY")

    def test_20_tooling_optimizer_and_crip_synthesis(self):
        """Pillar 3: Verifies Agent 12 Continuous Tooling Optimizer CRIP proposal synthesis."""
        from skills.tooling_optimizer import ToolingOptimizer
        optimizer = ToolingOptimizer(self.root)
        telemetry = optimizer.scan_telemetry("FEAT-L3-HWY-CHAUFFEUR")
        
        self.assertIn("identified_improvements", telemetry)
        self.assertGreaterEqual(len(telemetry["identified_improvements"]), 1)
        
        prop = telemetry["identified_improvements"][0]
        crip_doc = optimizer.generate_crip_document(prop)
        self.assertTrue(crip_doc.exists())
        self.assertTrue(crip_doc.name.endswith(".md"))

    def test_21_universal_llm_client_offline_mode(self):
        """Verifies UniversalLLMClient runs in offline simulation mode with no credentials."""
        from core.llm_client import UniversalLLMClient

        # Instantiate with no API key — should activate offline fallback
        client = UniversalLLMClient(api_key="", offline_fallback=True)
        self.assertTrue(client.offline_fallback)

        messages = [
            {"role": "system", "content": "You are a regulatory compliance agent."},
            {"role": "user", "content": "Query UNECE R157 requirements for ALKS operational speed."}
        ]
        # Offline fallback should produce a valid response dict (no API call)
        result = client.chat_completion(messages)
        self.assertIn("content", result)
        self.assertIn("model", result)
        self.assertIn("offline-sim", result["model"])

    def test_22_universal_llm_client_provider_resolution(self):
        """Verifies LLM client resolves provider from environment variables."""
        import os
        from core.llm_client import UniversalLLMClient

        # Simulate Ollama local LLM env
        os.environ["LLM_BASE_URL"] = "http://localhost:11434/v1"
        os.environ["LLM_MODEL"] = "llama3.2"
        client = UniversalLLMClient()
        self.assertIn("localhost:11434", client.base_url)
        self.assertEqual(client.model, "llama3.2")

        # Cleanup
        del os.environ["LLM_BASE_URL"]
        del os.environ["LLM_MODEL"]

    def test_23_tool_registry_registration_and_dispatch(self):
        """Verifies ToolRegistry correctly registers tools and dispatches calls."""
        from core.tool_registry import ToolRegistry

        registry = ToolRegistry()

        @registry.register(description="Returns double of the input integer.")
        def double_it(value: int) -> int:
            return value * 2

        # Verify tool registered
        defs = registry.get_tool_definitions()
        tool_names = [d["function"]["name"] for d in defs]
        self.assertIn("double_it", tool_names)

        # Verify schema generated correctly
        schema = next(d for d in defs if d["function"]["name"] == "double_it")
        self.assertEqual(schema["function"]["parameters"]["properties"]["value"]["type"], "integer")

        # Verify execution
        result = registry.execute_tool("double_it", {"value": 21})
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["result"], 42)

    def test_24_skeptical_web_fetcher_offline(self):
        """Verifies SkepticalWebFetcher runs in offline mode, applies skepticism, and detects kg deltas."""
        from tools.web_fetcher import SkepticalWebFetcher

        fetcher = SkepticalWebFetcher()

        # Fetch with offline simulation (no real HTTP call in sandboxed test)
        result = fetcher.fetch_live_regulation(
            query_or_url="https://unece.org/transport/documents/un-regulation-157",
            standard_id="UN_R157",
            max_age_days=180,
            allow_offline_sim=True
        )

        # Must return a structured result with skepticism audit
        self.assertIn(result["verdict"], [
            "ACCEPT_HIGH_CONFIDENCE", "ACCEPT_WITH_RESERVATIONS",
            "REJECT_DUBIOUS_SOURCE", "REJECT_UNREACHABLE"
        ])
        self.assertIn("confidence_score", result)
        self.assertIn("freshness", result)
        self.assertIn("skepticism_audit", result)
        self.assertIn("kg_delta_and_contradictions", result)

        # Domain must be in allowlist
        self.assertIn(result["source_domain"], [
            "unece.org", "eur-lex.europa.eu", "iso.org", "sae.org"
        ])

        # Skepticism must have fired domain trust
        self.assertGreater(result["skepticism_audit"]["domain_trust"], 0.5)

        # Freshness must be populated
        self.assertIn("is_stale", result["freshness"])
        self.assertIn("document_age_days", result["freshness"])

    def test_25_model_lock_provider_agnostic_config(self):
        """Verifies model_lock.json has provider-agnostic fields and tool-scoped network policy."""
        lock = self.runtime.model_lock
        # Provider-agnostic section must exist
        self.assertIn("provider_agnostic", lock["llm_configuration"])
        pa = lock["llm_configuration"]["provider_agnostic"]
        self.assertTrue(pa["enabled"])
        self.assertTrue(pa["offline_fallback"])
        self.assertIn("LLM_API_KEY", pa["env_resolution_order"])

        # live_network_allowed must still be False at framework level
        self.assertFalse(lock["tool_execution_policy"]["live_network_allowed"])

        # But specific tool and domains must be allowed
        self.assertIn("fetch_live_regulation", lock["tool_execution_policy"]["live_network_allowed_tools"])
        self.assertIn("unece.org", lock["tool_execution_policy"]["live_network_allowed_domains"])

if __name__ == "__main__":
    unittest.main()
