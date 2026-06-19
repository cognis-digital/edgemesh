"""The coding agent, exercised against a mock tool-calling backend."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from edgemesh.agent import Agent


class _ToolCallingBackend(BaseHTTPRequestHandler):
    """Turn 1: ask to write a file. Turn 2 (after tool result): finish."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        has_tool_result = any(m.get("role") == "tool" for m in body.get("messages", []))
        if not has_tool_result:
            msg = {"role": "assistant", "content": "",
                   "tool_calls": [{"id": "c1", "type": "function",
                                   "function": {"name": "write_file",
                                                "arguments": json.dumps({"path": "out.txt",
                                                                         "content": "done"})}}]}
        else:
            msg = {"role": "assistant", "content": "Created out.txt. Task complete."}
        out = json.dumps({"choices": [{"message": msg}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture()
def backend():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _ToolCallingBackend)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def test_agent_executes_tool_then_finishes(backend, tmp_path):
    events = []
    agent = Agent("mock", base_url=backend, root=str(tmp_path),
                  on_event=lambda k, d: events.append((k, d)))
    res = agent.run("create out.txt with the text done")
    assert res.ok
    assert "complete" in res.final.lower()
    assert (tmp_path / "out.txt").read_text() == "done"      # the tool really ran
    assert any(k == "tool" and d["name"] == "write_file" for k, d in events)
    assert res.steps == 2


def test_agent_handles_dead_gateway(tmp_path):
    res = Agent("mock", base_url="http://127.0.0.1:1", root=str(tmp_path)).run("x")
    assert not res.ok
    assert "failed" in res.final.lower()
