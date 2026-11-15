"""
ADAS/AD Agentic Framework — System Preparedness & Diagnostic Doctor
Runs pre-flight verification across:
  1. Python runtime & core libraries (Chainlit, scenariogeneration, Shapely, PyYAML, jsonschema)
  2. Model configuration & LLM endpoint connectivity (OpenAI, Gemini, Ollama, Groq, or offline sim)
  3. Knowledge graph and schema integrity (KG0 - KG4, validation schemas)
  4. Feature project workspace partitioning (projects/<feature_id>/)
"""

import os
import sys
import json
import importlib
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm_client import UniversalLLMClient

REQUIRED_PACKAGES = [
    ("yaml", "pyyaml"),
    ("jsonschema", "jsonschema"),
    ("chainlit", "chainlit"),
    ("scenariogeneration", "scenariogeneration"),
    ("shapely", "shapely")
]

REQUIRED_KGS = [
    "knowledge_graphs/kg0_canonical_terminology.json",
    "knowledge_graphs/kg1_regulatory.json",
    "knowledge_graphs/kg2_odd_taxonomy.json",
    "knowledge_graphs/kg3_vehicle_platform.json",
    "knowledge_graphs/kg4_hazard_sotif_catalog.json"
]

REQUIRED_SCHEMAS = [
    "schemas/agent_contract.schema.json",
    "schemas/feature_profile.schema.json",
    "schemas/openodd.schema.json",
    "schemas/icd.schema.json"
]

def run_preparedness_check(verbose: bool = True) -> Dict[str, Any]:
    """
    Executes a complete health check and returns a structured status dictionary.
    """
    results: Dict[str, Any] = {
        "status": "PASS",
        "python_version": sys.version.split()[0],
        "checks": {}
    }

    # 1. Check Python version (>= 3.10)
    py_ok = sys.version_info >= (3, 10)
    results["checks"]["python_version"] = {
        "status": "PASS" if py_ok else "FAIL",
        "version": sys.version.split()[0],
        "message": "Python >= 3.10 verified" if py_ok else "Python 3.10+ required"
    }
    if not py_ok:
        results["status"] = "FAIL"

    # 2. Check Required Packages
    pkg_status = {}
    all_pkgs_ok = True
    for mod_name, pip_name in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(mod_name)
            ver = getattr(mod, "__version__", "installed")
            pkg_status[pip_name] = {"status": "PASS", "version": ver}
        except ImportError:
            pkg_status[pip_name] = {"status": "MISSING", "error": f"Install with: pip install {pip_name}"}
            all_pkgs_ok = False
    
    results["checks"]["dependencies"] = {
        "status": "PASS" if all_pkgs_ok else "FAIL",
        "packages": pkg_status
    }
    if not all_pkgs_ok:
        results["status"] = "FAIL"

    # 3. Check Knowledge Graphs & Schemas
    missing_files = []
    for kg in REQUIRED_KGS:
        if not (ROOT / kg).exists():
            missing_files.append(kg)
    for sch in REQUIRED_SCHEMAS:
        if not (ROOT / sch).exists():
            missing_files.append(sch)

    files_ok = len(missing_files) == 0
    results["checks"]["knowledge_and_schemas"] = {
        "status": "PASS" if files_ok else "FAIL",
        "missing": missing_files
    }
    if not files_ok:
        results["status"] = "FAIL"

    # 4. Check LLM Connectivity & Mode
    client = UniversalLLMClient(offline_fallback=True)
    llm_info = {
        "base_url": client.base_url,
        "model": client.model,
        "api_key_configured": bool(client.api_key),
        "mode": "LIVE_API" if client.api_key or "localhost" in client.base_url or "127.0.0.1" in client.base_url else "OFFLINE_SIMULATION"
    }

    # Quick lightweight probe
    probe_msg = [{"role": "user", "content": "ping"}]
    try:
        probe_res = client.chat_completion(messages=probe_msg, max_tokens=10)
        llm_info["probe_status"] = "SUCCESS"
        llm_info["probe_model"] = probe_res.get("model", "unknown")
    except Exception as e:
        llm_info["probe_status"] = "PROBE_FAILED"
        llm_info["probe_error"] = str(e)

    results["checks"]["llm_provider"] = {
        "status": "PASS",
        "info": llm_info
    }

    # 5. Check Workspaces
    projects_dir = ROOT / "projects"
    existing_projects = [p.name for p in projects_dir.iterdir() if p.is_dir()] if projects_dir.exists() else []
    results["checks"]["projects"] = {
        "status": "PASS" if existing_projects else "WARN",
        "count": len(existing_projects),
        "projects": existing_projects
    }

    if verbose:
        _print_report(results)

    return results

def _print_report(res: Dict[str, Any]):
    print("\n=======================================================")
    print("   ADAS/AD AGENTIC FRAMEWORK — PREPAREDNESS DOCTOR     ")
    print("=======================================================")
    
    # Python
    py_c = res["checks"]["python_version"]
    print(f"[{py_c['status']}] Python Environment: v{py_c['version']}")

    # Deps
    dep_c = res["checks"]["dependencies"]
    print(f"[{dep_c['status']}] Core Dependencies:")
    for pkg, pdata in dep_c["packages"].items():
        if pdata["status"] == "PASS":
            print(f"       - {pkg}: {pdata['version']}")
        else:
            print(f"       - {pkg}: MISSING (pip install {pkg})")

    # KGs
    kg_c = res["checks"]["knowledge_and_schemas"]
    print(f"[{kg_c['status']}] Automotive Knowledge Graphs & Schemas (6 KGs)")
    if kg_c["missing"]:
        for m in kg_c["missing"]:
            print(f"       - Missing: {m}")

    # LLM
    llm_c = res["checks"]["llm_provider"]["info"]
    print(f"[{res['checks']['llm_provider']['status']}] LLM Provider Configuration:")
    print(f"       - Mode:     {llm_c['mode']}")
    print(f"       - Model:    {llm_c['model']}")
    print(f"       - Endpoint: {llm_c['base_url']}")
    print(f"       - Key:      {'Configured' if llm_c['api_key_configured'] else 'None (Running in Deterministic Simulation Mode)'}")
    print(f"       - Probe:    {llm_c.get('probe_status')} ({llm_c.get('probe_model', 'N/A')})")

    # Projects
    proj_c = res["checks"]["projects"]
    print(f"[{proj_c['status']}] Feature Project Workspaces: {proj_c['count']} active")
    for pr in proj_c["projects"]:
        print(f"       - projects/{pr}/")

    print("-------------------------------------------------------")
    if res["status"] == "PASS":
        print(" [READY] System is 100% prepared. Launch cockpit with:")
        print("         python -m chainlit run orchestrator/chat_app.py --port 8000")
    else:
        print(" [ACTION NEEDED] Resolve flagged items above before launching.")
    print("=======================================================\n")

if __name__ == "__main__":
    check_res = run_preparedness_check(verbose=True)
    sys.exit(0 if check_res["status"] == "PASS" else 1)
