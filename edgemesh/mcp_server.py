"""An MCP (Model Context Protocol) server exposing edgemesh to any MCP client.

This is the bridge to VSCode's agent tooling: GitHub Copilot, Cline, Continue,
Cursor, Claude Desktop/Code, and anything else that speaks MCP can mount this
server and instantly gain edgemesh's developer toolbelt (files, search, shell,
tests, git) *and* its models (run the local fleet / cluster as a tool).

Transport: MCP stdio — newline-delimited JSON-RPC 2.0 on stdin/stdout. Pure
standard library; no third-party MCP SDK required.

Run:  edgemesh mcp [--root DIR] [--gateway URL]
"""

from __future__ import annotations

import json
import sys
import urllib.request

from edgemesh.devtools import Toolbelt, dispatch, mcp_tools, TOOL_NAMES

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "edgemesh", "version": "0.13.0"}

# Two extra tools beyond the raw toolbelt: run the coding agent, or chat a model.
_EXTRA_TOOLS = [
    {"name": "edgemesh_agent",
     "description": "Run the edgemesh senior-engineer coding agent on a task. It will "
                    "read/edit files, run tests and use git autonomously, powered by an "
                    "edgemesh model. Returns a summary of what it did.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string"}, "model": {"type": "string"},
         "max_steps": {"type": "integer"}}, "required": ["task"]}},
    {"name": "edgemesh_chat",
     "description": "Ask an edgemesh model a one-shot question (uses the local fleet / "
                    "cluster behind the gateway). Returns the model's reply.",
     "inputSchema": {"type": "object", "properties": {
         "prompt": {"type": "string"}, "model": {"type": "string"}},
      "required": ["prompt"]}},
]


def _default_model(gateway: str) -> str:
    try:
        with urllib.request.urlopen(f"{gateway.rstrip('/')}/v1/models", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8", "replace")).get("data", [])
        return data[0]["id"] if data else ""
    except Exception:  # noqa: BLE001
        return ""


def _chat_once(gateway: str, model: str, prompt: str) -> str:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{gateway.rstrip('/')}/v1/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        body = json.loads(r.read().decode("utf-8", "replace"))
    return ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "") or "(no reply)"


class MCPServer:
    def __init__(self, root: str = ".", gateway: str = "http://127.0.0.1:8780") -> None:
        self.belt = Toolbelt(root)
        self.gateway = gateway

    # ── tool execution ─────────────────────────────────────────────────────────
    def _call_tool(self, name: str, args: dict) -> tuple[str, bool]:
        """Return (text, is_error)."""
        if name in TOOL_NAMES:
            out = dispatch(self.belt, name, args)
            return out, out.startswith("error:")
        if name == "edgemesh_chat":
            model = args.get("model") or _default_model(self.gateway)
            if not model:
                return "no model available from the gateway", True
            try:
                return _chat_once(self.gateway, model, args.get("prompt", "")), False
            except Exception as exc:  # noqa: BLE001
                return f"chat failed: {exc}", True
        if name == "edgemesh_agent":
            from edgemesh.agent import Agent
            model = args.get("model") or _default_model(self.gateway)
            if not model:
                return "no model available from the gateway", True
            try:
                res = Agent(model, base_url=self.gateway, root=str(self.belt.root),
                            max_steps=int(args.get("max_steps", 24))).run(args.get("task", ""))
                return f"{res.final}\n\n[{res.steps} steps, {len(res.tool_calls)} tool calls]", not res.ok
            except Exception as exc:  # noqa: BLE001
                return f"agent failed: {exc}", True
        return f"unknown tool: {name}", True

    # ── JSON-RPC dispatch ───────────────────────────────────────────────────────
    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            return self._ok(mid, {"protocolVersion": PROTOCOL_VERSION,
                                  "capabilities": {"tools": {}},
                                  "serverInfo": SERVER_INFO})
        if method in ("notifications/initialized", "initialized"):
            return None  # notification, no reply
        if method == "ping":
            return self._ok(mid, {})
        if method == "tools/list":
            return self._ok(mid, {"tools": mcp_tools() + _EXTRA_TOOLS})
        if method == "tools/call":
            name = params.get("name", "")
            text, is_err = self._call_tool(name, params.get("arguments") or {})
            return self._ok(mid, {"content": [{"type": "text", "text": text}], "isError": is_err})
        if mid is not None:
            return self._err(mid, -32601, f"method not found: {method}")
        return None

    @staticmethod
    def _ok(mid, result) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _err(mid, code, message) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    # ── stdio loop ──────────────────────────────────────────────────────────────
    def serve_stdio(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            reply = self.handle(msg)
            if reply is not None:
                stdout.write(json.dumps(reply) + "\n")
                stdout.flush()


def run(root: str = ".", gateway: str = "http://127.0.0.1:8780") -> int:
    MCPServer(root, gateway).serve_stdio()
    return 0


__all__ = ["MCPServer", "run"]
