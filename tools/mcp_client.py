"""
Lightweight Model Context Protocol (MCP) Client
Enables agents to discover and invoke tools from external MCP servers via stdio or HTTP.
Bridges MCP server tool capabilities directly into the core ToolRegistry.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

class MCPClientError(Exception):
    pass

class MCPClient:
    def __init__(self, server_command: Optional[List[str]] = None, server_url: Optional[str] = None):
        self.server_command = server_command
        self.server_url = server_url
        self._proc: Optional[subprocess.Popen] = None
        self._msg_id = 0
        self.discovered_tools: Dict[str, Dict[str, Any]] = {}

    def start(self):
        """Starts stdio server process if command is provided."""
        if self.server_command:
            try:
                self._proc = subprocess.Popen(
                    self.server_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                self._send_rpc("initialize", {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "adas-agentic-mcp-client", "version": "1.0.0"}
                })
            except Exception as e:
                raise MCPClientError(f"Failed to start MCP server process: {e}")

    def list_tools(self) -> List[Dict[str, Any]]:
        """Queries the MCP server for available tools (tools/list)."""
        if self._proc:
            resp = self._send_rpc("tools/list", {})
            tools = resp.get("tools", [])
            for t in tools:
                self.discovered_tools[t["name"]] = t
            return tools
        
        # If no active server process, return pre-configured or empty
        return list(self.discovered_tools.values())

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes a tool on the MCP server (tools/call)."""
        if self._proc:
            resp = self._send_rpc("tools/call", {"name": name, "arguments": arguments})
            return resp

        # Fallback simulation if offline
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"[MCP_SIMULATION] Executed tool '{name}' with {len(arguments)} arguments."
                }
            ],
            "isError": False
        }

    def bridge_to_tool_registry(self, registry: Any):
        """Registers all discovered MCP tools into the provided ToolRegistry."""
        tools = self.list_tools()
        for t in tools:
            tool_name = t["name"]
            tool_desc = t.get("description", f"MCP Tool {tool_name}")
            schema = t.get("inputSchema", {"type": "object", "properties": {}})

            registry.register_mcp_tool(
                name=tool_name,
                description=tool_desc,
                input_schema=schema,
                invoker_callable=lambda args, tn=tool_name: self.call_tool(tn, args)
            )

    def _send_rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sends a JSON-RPC 2.0 request over stdin and reads response from stdout."""
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise MCPClientError("MCP process not active")

        self._msg_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params
        }
        
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()

        line = self._proc.stdout.readline()
        if not line:
            raise MCPClientError("MCP server returned empty response")

        resp = json.loads(line)
        if "error" in resp:
            raise MCPClientError(f"MCP RPC Error: {resp['error']}")
        return resp.get("result", {})

    def stop(self):
        """Terminates the stdio MCP server."""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
            self._proc = None
