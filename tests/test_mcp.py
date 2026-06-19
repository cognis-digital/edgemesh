"""MCP server: JSON-RPC handshake, tool listing, and tool execution."""

from __future__ import annotations

import io

from edgemesh.devtools import TOOL_NAMES
from edgemesh.mcp_server import MCPServer


def _server(tmp_path):
    return MCPServer(root=str(tmp_path))


def test_initialize(tmp_path):
    r = _server(tmp_path).handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert r["result"]["serverInfo"]["name"] == "edgemesh"
    assert "tools" in r["result"]["capabilities"]


def test_notification_returns_none(tmp_path):
    assert _server(tmp_path).handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_includes_toolbelt_and_extras(tmp_path):
    r = _server(tmp_path).handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = {t["name"] for t in r["result"]["tools"]}
    assert set(TOOL_NAMES) <= names
    assert {"edgemesh_agent", "edgemesh_chat"} <= names


def test_tools_call_runs_toolbelt(tmp_path):
    (tmp_path / "hello.txt").write_text("hi there", encoding="utf-8")
    r = _server(tmp_path).handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                  "params": {"name": "read_file", "arguments": {"path": "hello.txt"}}})
    assert r["result"]["isError"] is False
    assert "hi there" in r["result"]["content"][0]["text"]


def test_unknown_method(tmp_path):
    r = _server(tmp_path).handle({"jsonrpc": "2.0", "id": 9, "method": "bogus/thing"})
    assert r["error"]["code"] == -32601


def test_stdio_loop_roundtrip(tmp_path):
    stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n')
    stdout = io.StringIO()
    _server(tmp_path).serve_stdio(stdin=stdin, stdout=stdout)
    import json
    out = json.loads(stdout.getvalue().strip())
    assert out["id"] == 1 and len(out["result"]["tools"]) >= len(TOOL_NAMES)
