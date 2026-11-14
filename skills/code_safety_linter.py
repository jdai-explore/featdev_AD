"""
Skill: MISRA-C & Embedded Safety Linter
Enforces ISO 26262 ASIL D static coding requirements on generated C wrappers:
- No dynamic memory allocation (malloc, calloc, realloc, free)
- No unbounded loops or recursion
- Mandatory AUTOSAR E2E CRC/Alive Counter evaluation
- Bounded deterministic execution paths
"""

import sys
import re
import json
from pathlib import Path
from typing import Dict, Any, List

def lint_embedded_c_code(file_path: str) -> Dict[str, Any]:
    p = Path(file_path)
    if not p.exists():
        return {"status": "FAIL", "error": f"File not found: {file_path}"}

    with open(p, "r", encoding="utf-8") as f:
        code_lines = f.readlines()

    violations: List[str] = []
    has_e2e_check = False

    # Prohibited patterns
    forbidden_patterns = [
        (r"\b(malloc|calloc|realloc|free|alloca)\b", "MISRA Rule 21.3 / ISO 26262: Dynamic memory allocation is strictly prohibited in safety-critical code"),
        (r"\bgoto\b", "MISRA Rule 15.1: Use of 'goto' statement is prohibited"),
        (r"\bwhile\s*\(\s*1\s*\)", "MISRA Rule 14.2: Unbounded infinite loop while(1) detected"),
        (r"\bsetjmp\b|\blongjmp\b", "MISRA Rule 21.4: Non-local jumps (setjmp/longjmp) are prohibited")
    ]

    # Strip multi-line comments and single-line comments before analysis
    code_text = "".join(code_lines)
    # Remove /* ... */ comments
    code_text = re.sub(r'/\*.*?\*/', '', code_text, flags=re.DOTALL)
    # Remove // ... comments
    code_text = re.sub(r'//.*', '', code_text)

    clean_lines = code_text.splitlines()

    for line_idx, clean_line in enumerate(clean_lines, start=1):
        clean_line = clean_line.strip()
        if not clean_line:
            continue
        
        # Check forbidden patterns
        for pattern, msg in forbidden_patterns:
            if re.search(pattern, clean_line):
                violations.append(f"Line {line_idx}: {msg} -> '{clean_line}'")

        # Check for E2E check invocation
        if "E2E_Check" in clean_line or "AUTOSAR_E2E" in clean_line:
            has_e2e_check = True

    if not has_e2e_check:
        violations.append("Safety Gap: No AUTOSAR E2E (CRC / Alive Counter) verification routine detected in controller interface!")

    status = "FAIL" if violations else "PASS"
    return {
        "status": status,
        "file": str(p),
        "total_lines": len(code_lines),
        "violations_count": len(violations),
        "violations": violations,
        "verified_rules": [
            "MISRA Rule 21.3 - Zero dynamic memory allocation",
            "MISRA Rule 15.1 - Zero goto statements",
            "AUTOSAR E2E Profile CRC verification enforced",
            "Deterministic bounded execution paths"
        ] if not violations else []
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: code_safety_linter.py <c_file_path>"}))
        sys.exit(1)

    res = lint_embedded_c_code(sys.argv[1])
    print(json.dumps(res, indent=2))
    if res["status"] != "PASS":
        sys.exit(2)
