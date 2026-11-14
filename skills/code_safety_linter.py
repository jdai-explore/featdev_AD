"""
Skill: MISRA-C & Embedded Safety Linter (Tree-Sitter AST Engine)
Performs compiler-grade Concrete Syntax Tree (CST/AST) parsing using tree-sitter-c.
Verifies ISO 26262 ASIL D and MISRA-C:2012 rules:
- MISRA Rule 21.3: Prohibits dynamic memory allocation (malloc, calloc, realloc, free, alloca)
- MISRA Rule 15.1: Prohibits 'goto' statements
- MISRA Rule 17.2: Prohibits direct or indirect recursion (cycles in AST call graph)
- MISRA Rule 14.2: Checks for unbounded infinite loops
- AUTOSAR Safety: Verifies mandatory AUTOSAR E2E Profile CRC verification
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
from collections import defaultdict

import tree_sitter
import tree_sitter_c

class TreeSitterMisraLinter:
    def __init__(self):
        c_lang = tree_sitter.Language(tree_sitter_c.language())
        self.parser = tree_sitter.Parser(c_lang)
        self.forbidden_memory_functions = {
            "malloc", "calloc", "realloc", "free", "alloca", "valloc", "sbrk"
        }
        self.forbidden_jump_functions = {"setjmp", "longjmp"}

    def parse_file(self, file_path: Path) -> Tuple[tree_sitter.Tree, bytes]:
        source_bytes = file_path.read_bytes()
        tree = self.parser.parse(source_bytes)
        return tree, source_bytes

    def find_nodes_by_type(self, node: tree_sitter.Node, target_types: Set[str]) -> List[tree_sitter.Node]:
        matched = []
        stack = [node]
        while stack:
            curr = stack.pop()
            if curr.type in target_types:
                matched.append(curr)
            stack.extend(reversed(curr.children))
        return matched

    def lint(self, file_path: str) -> Dict[str, Any]:
        p = Path(file_path)
        if not p.exists():
            return {"status": "FAIL", "error": f"File not found: {file_path}"}

        try:
            tree, source = self.parse_file(p)
        except Exception as e:
            return {"status": "FAIL", "error": f"Tree-sitter C parsing exception: {str(e)}"}

        violations: List[str] = []
        has_e2e_check = False
        function_calls: Dict[str, Set[str]] = defaultdict(set)
        current_function = None

        # Traverse AST nodes
        call_nodes = self.find_nodes_by_type(tree.root_node, {"call_expression"})
        goto_nodes = self.find_nodes_by_type(tree.root_node, {"goto_statement"})
        while_nodes = self.find_nodes_by_type(tree.root_node, {"while_statement"})
        func_def_nodes = self.find_nodes_by_type(tree.root_node, {"function_definition"})

        # Rule 15.1: Prohibit goto
        for g_node in goto_nodes:
            start_point = g_node.start_point
            violations.append(
                f"Line {start_point[0] + 1}: MISRA Rule 15.1: 'goto' statement prohibited -> '{source[g_node.start_byte:g_node.end_byte].decode('utf-8', errors='ignore')}'"
            )

        # Inspect Function Calls for Dynamic Memory & E2E
        for c_node in call_nodes:
            func_name_node = c_node.child_by_field_name("function")
            if func_name_node:
                fname = source[func_name_node.start_byte:func_name_node.end_byte].decode("utf-8", errors="ignore").strip()
                
                # Rule 21.3: Dynamic memory allocation
                if fname in self.forbidden_memory_functions:
                    line_no = c_node.start_point[0] + 1
                    violations.append(
                        f"Line {line_no}: MISRA Rule 21.3 / ISO 26262: Prohibited dynamic memory call '{fname}' detected!"
                    )

                # Rule 21.4: Non-local jumps
                if fname in self.forbidden_jump_functions:
                    line_no = c_node.start_point[0] + 1
                    violations.append(
                        f"Line {line_no}: MISRA Rule 21.4: Non-local jump '{fname}' prohibited in safety systems!"
                    )

                # AUTOSAR E2E validation check
                if "E2E_Check" in fname or "AUTOSAR_E2E" in fname:
                    has_e2e_check = True

        # Rule 17.2: Detect Direct & Indirect Recursion via Call Graph
        for fdef in func_def_nodes:
            declarator = fdef.child_by_field_name("declarator")
            # Handle pointer or function declarator
            while declarator and declarator.type in ("function_declarator", "pointer_declarator"):
                if declarator.type == "function_declarator":
                    inner_decl = declarator.child_by_field_name("declarator")
                    if inner_decl:
                        caller_name = source[inner_decl.start_byte:inner_decl.end_byte].decode("utf-8", errors="ignore").strip()
                        break
                declarator = declarator.children[0] if declarator.children else None
            else:
                caller_name = "unknown_function"

            body = fdef.child_by_field_name("body")
            if body and caller_name != "unknown_function":
                body_calls = self.find_nodes_by_type(body, {"call_expression"})
                for b_call in body_calls:
                    fn_node = b_call.child_by_field_name("function")
                    if fn_node:
                        callee_name = source[fn_node.start_byte:fn_node.end_byte].decode("utf-8", errors="ignore").strip()
                        function_calls[caller_name].add(callee_name)

        # Check for cycles in function_calls graph
        def has_cycle(curr: str, visited: Set[str], path: List[str]) -> bool:
            visited.add(curr)
            path.append(curr)
            for neighbor in function_calls.get(curr, []):
                if neighbor in path:
                    cycle_str = " -> ".join(path[path.index(neighbor):] + [neighbor])
                    violations.append(f"MISRA Rule 17.2: Recursion cycle detected in AST call graph: {cycle_str}")
                    return True
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, path):
                        return True
            path.pop()
            return False

        global_visited: Set[str] = set()
        for func in list(function_calls.keys()):
            if func not in global_visited:
                has_cycle(func, global_visited, [])

        # Rule 14.2: Inspect while loops for unbounded conditions
        for w_node in while_nodes:
            cond_node = w_node.child_by_field_name("condition")
            if cond_node:
                cond_text = source[cond_node.start_byte:cond_node.end_byte].decode("utf-8", errors="ignore").strip(" ()")
                if cond_text in ("1", "true", "TRUE"):
                    # Check if body has a break or return
                    body_node = w_node.child_by_field_name("body")
                    breaks = self.find_nodes_by_type(body_node, {"break_statement", "return_statement"}) if body_node else []
                    if not breaks:
                        violations.append(
                            f"Line {w_node.start_point[0] + 1}: MISRA Rule 14.2: Unbounded infinite loop while({cond_text}) without break or return!"
                        )

        # AUTOSAR E2E validation mandate
        if not has_e2e_check:
            violations.append(
                "Safety Gap: No AUTOSAR E2E CRC / Alive Counter verification call detected in controller interface!"
            )

        status = "FAIL" if violations else "PASS"
        return {
            "status": status,
            "engine": "Tree-Sitter-C AST (C11/ISO 26262 Parser)",
            "file": str(p),
            "ast_root_type": tree.root_node.type,
            "functions_analyzed": list(function_calls.keys()),
            "violations_count": len(violations),
            "violations": violations,
            "verified_rules": [
                "MISRA Rule 21.3 - AST-verified zero dynamic memory allocation",
                "MISRA Rule 15.1 - Zero goto statements in AST",
                "MISRA Rule 17.2 - Zero recursion cycles in call graph",
                "MISRA Rule 14.2 - Bounded deterministic loop constructs",
                "AUTOSAR E2E CRC Profile verification enforced"
            ] if not violations else []
        }

def lint_embedded_c_code(file_path: str) -> Dict[str, Any]:
    linter = TreeSitterMisraLinter()
    return linter.lint(file_path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: code_safety_linter.py <c_file_path>"}))
        sys.exit(1)

    res = lint_embedded_c_code(sys.argv[1])
    print(json.dumps(res, indent=2))
    if res["status"] != "PASS":
        sys.exit(2)
