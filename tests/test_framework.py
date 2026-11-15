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
        """Validates all 11 Agent YAML contracts against agent_contract.schema.json."""
        schema_path = self.root / "schemas/agent_contract.schema.json"
        with open(schema_path, "r", encoding="utf-8") as sf:
            schema = json.load(sf)

        agent_files = list((self.root / "agents").glob("*.yaml"))
        self.assertEqual(len(agent_files), 11, "Must have exactly 11 agent contracts")

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

if __name__ == "__main__":
    unittest.main()
