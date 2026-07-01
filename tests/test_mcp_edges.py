"""MCP server error paths and protocol edge cases."""

from __future__ import annotations

from edgemesh.mcp_server import MCPServer


def _srv(tmp_path):
    return MCPServer(root=str(tmp_path))


def test_initialize_reports_protocol_version(tmp_path):
    r = _srv(tmp_path).handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert "protocolVersion" in r["result"]


def test_unknown_method_returns_method_not_found(tmp_path):
    r = _srv(tmp_path).handle({"jsonrpc": "2.0", "id": 5, "method": "no/such"})
    assert r["error"]["code"] == -32601


def test_notification_has_no_response(tmp_path):
    assert _srv(tmp_path).handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_call_unknown_tool_errors(tmp_path):
    r = _srv(tmp_path).handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "no_such_tool", "arguments": {}}})
    # either a JSON-RPC error or an isError tool result — both signal failure
    assert ("error" in r) or (r.get("result", {}).get("isError") is True)


def test_tools_call_read_missing_file_reports_error(tmp_path):
    r = _srv(tmp_path).handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                               "params": {"name": "read_file",
                                          "arguments": {"path": "does_not_exist.txt"}}})
    assert r["result"]["isError"] is True


def test_tools_call_write_then_read(tmp_path):
    srv = _srv(tmp_path)
    w = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "write_file",
                               "arguments": {"path": "note.txt", "content": "hello"}}})
    assert w["result"]["isError"] is False
    r = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "read_file", "arguments": {"path": "note.txt"}}})
    assert "hello" in r["result"]["content"][0]["text"]


def test_tools_list_each_tool_has_schema(tmp_path):
    r = _srv(tmp_path).handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    for tool in r["result"]["tools"]:
        assert "name" in tool and "inputSchema" in tool


def test_response_echoes_request_id(tmp_path):
    r = _srv(tmp_path).handle({"jsonrpc": "2.0", "id": 77, "method": "tools/list"})
    assert r["id"] == 77
