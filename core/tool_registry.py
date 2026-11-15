"""
Tool Registry for Autonomous ADAS/AD Agents
Enables dynamic tool registration, parameter schema generation,
and execution dispatch compatible with standard OpenAI/JSON tool-calling specifications.
"""

import inspect
import json
from typing import Dict, Any, List, Callable, Optional, get_type_hints

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters_schema: Optional[Dict[str, Any]] = None
    ):
        """
        Decorator or direct call to register a Python function as an agent tool.
        If parameters_schema is omitted, it is inferred from Python type hints and docstrings.
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or (inspect.getdoc(func) or f"Executes {tool_name}").strip()

            schema = parameters_schema or self._generate_schema_from_signature(func)

            tool_def = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_desc,
                    "parameters": schema
                }
            }

            self._tools[tool_name] = func
            self._schemas[tool_name] = tool_def
            return func

        return decorator

    def register_tool(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters_schema: Optional[Dict[str, Any]] = None
    ):
        """Direct registration method without decorator syntax."""
        return self.register(name, description, parameters_schema)(func)

    def register_mcp_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        invoker_callable: Callable[[Dict[str, Any]], Any]
    ):
        """Bridges an external MCP tool into the native tool registry."""
        tool_def = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": input_schema
            }
        }
        self._tools[name] = lambda **kwargs: invoker_callable(kwargs)
        self._schemas[name] = tool_def

    def get_tool_definitions(self, tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Returns the list of tool definitions formatted for LLM consumption."""
        if tool_names is None:
            return list(self._schemas.values())
        return [self._schemas[name] for name in tool_names if name in self._schemas]

    def execute_tool(self, name: str, arguments: Dict[str, Any] or str) -> Dict[str, Any]:
        """Executes a registered tool by name with arguments."""
        if name not in self._tools:
            return {
                "status": "ERROR",
                "tool": name,
                "error": f"Tool '{name}' is not registered in ToolRegistry"
            }

        func = self._tools[name]
        if isinstance(arguments, str):
            try:
                kwargs = json.loads(arguments)
            except Exception as e:
                return {
                    "status": "ERROR",
                    "tool": name,
                    "error": f"Failed to parse tool arguments JSON: {e}"
                }
        else:
            kwargs = arguments or {}

        try:
            result = func(**kwargs)
            return {
                "status": "SUCCESS",
                "tool": name,
                "result": result
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "tool": name,
                "error": str(e)
            }

    def _generate_schema_from_signature(self, func: Callable) -> Dict[str, Any]:
        """Infers JSON schema parameters from function signature and type hints."""
        sig = inspect.signature(func)
        type_hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
        
        properties: Dict[str, Any] = {}
        required: List[str] = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = type_hints.get(param_name, str)
            # Handle typing.Optional
            origin = getattr(param_type, "__origin__", None)
            args = getattr(param_type, "__args__", ())
            if origin is not None and type(None) in args:
                actual_types = [a for a in args if a is not type(None)]
                param_type = actual_types[0] if actual_types else str

            json_type = type_map.get(param_type, "string")
            properties[param_name] = {
                "type": json_type,
                "description": f"Parameter {param_name}"
            }

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
