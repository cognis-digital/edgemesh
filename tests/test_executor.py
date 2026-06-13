"""Distributed execution + scatter-gather over the swarm, exercised against a
mock OpenAI backend (a real socket server that echoes the prompt)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from edgemesh.executor import content_of, needs_sharding, run_job, scatter_gather
from edgemesh.protocol import CLASS_C, HardwareProfile, Job, NodeInfo
from edgemesh.swarm import SwarmController


class _MockBackend(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        prompt = body.get("messages", [{}])[-1].get("content", "")
        out = json.dumps({"choices": [{"message": {"role": "assistant",
                                                    "content": f"echo:{prompt}"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture()
def backend():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _MockBackend)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _node(nid, endpoint, vram=12000):
    return NodeInfo(node_id=nid, name=nid, node_class=CLASS_C, endpoint=endpoint,
                    profile=HardwareProfile(os="Linux", arch="x86_64", accelerator="cuda",
                                            ram_mb=32000, vram_mb=vram, gpu_name="GPU"))


def test_content_of():
    assert content_of({"choices": [{"message": {"content": "hi"}}]}) == "hi"
    assert content_of({"bad": 1}) == ""


def test_run_job_executes_and_settles(backend):
    sc = SwarmController()
    sc.ledger.grant("buyer", 10)
    sc.register(_node("n1", backend))
    job = Job.new("testmodel", min_vram_mb=4000)
    res = run_job(sc, job, {"messages": [{"role": "user", "content": "ping"}]}, "buyer", price=2.0)
    assert res["ok"] and res["node_id"] == "n1"
    assert content_of(res["result"]) == "echo:ping"
    assert res["paid"] == 2.0
    assert sc.ledger.balance("n1") == 2.0 and sc.ledger.balance("buyer") == 8.0


def test_run_job_needs_sharding_when_model_too_big(backend):
    sc = SwarmController()
    sc.register(_node("n1", backend, vram=2000))
    res = run_job(sc, Job.new("huge", min_vram_mb=999999),
                  {"messages": [{"role": "user", "content": "x"}]}, "buyer")
    assert not res["ok"] and "sharding-capable" in res["error"]


def test_run_job_no_endpoint_is_not_runnable():
    sc = SwarmController()
    node = _node("n1", "")  # registered but not servable
    sc.register(node)
    res = run_job(sc, Job.new("m"), {"messages": []}, "buyer")
    assert not res["ok"]


def test_scatter_gather_distributes_and_aggregates(backend):
    sc = SwarmController()
    sc.register(_node("a", backend))
    sc.register(_node("b", backend))
    prompts = ["one", "two", "three", "four"]
    res = scatter_gather(sc, "testmodel", prompts, aggregate="all")
    assert res["ok"] and res["count"] == 4
    assert {r["content"] for r in res["result"]} == {f"echo:{p}" for p in prompts}
    assert len(res["nodes_used"]) >= 1  # round-robined across a/b

    concat = scatter_gather(sc, "testmodel", ["x", "y"], aggregate="concat")
    assert concat["result"] == "echo:x\necho:y"

    vote = scatter_gather(sc, "testmodel", ["same", "same", "same"], aggregate="vote")
    assert vote["result"] == "echo:same"


def test_needs_sharding_helper():
    assert needs_sharding(Job.new("m", min_vram_mb=999999), [_node("a", "u", vram=1000)])
    assert not needs_sharding(Job.new("m", min_vram_mb=1000), [_node("a", "u", vram=8000)])
