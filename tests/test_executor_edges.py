"""Executor edge cases: run_job failover + settlement, sharding error message,
scatter_gather aggregation modes, StreamMeter, and metered_stream billing."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from edgemesh.executor import (StreamMeter, content_of, metered_stream,
                               needs_sharding, run_job, scatter_gather)
from edgemesh.protocol import CLASS_C, HardwareProfile, Job, NodeInfo
from edgemesh.swarm import SwarmController


def _node(nid, vram=8000, accel="cuda", endpoint="", sharding=False):
    return NodeInfo(node_id=nid, name=nid, node_class=CLASS_C, endpoint=endpoint,
                    profile=HardwareProfile(os="L", arch="x", accelerator=accel,
                                            ram_mb=32000, vram_mb=vram, gpu_name="G"),
                    sharding=sharding)


# --- a controllable in-process backend ---------------------------------------
class _Backend(BaseHTTPRequestHandler):
    MODE = "ok"  # ok | fail | echo

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.MODE == "fail":
            self.send_response(500)
            self.end_headers()
            return
        content = body.get("messages", [{}])[-1].get("content", "?") if body.get("messages") else "pong"
        out = json.dumps({"choices": [{"message": {"content": f"echo:{content}"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def _spawn(mode="ok"):
    handler = type("H", (_Backend,), {"MODE": mode})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


# --- content_of --------------------------------------------------------------
def test_content_of_extracts_message():
    assert content_of({"choices": [{"message": {"content": "hi"}}]}) == "hi"


def test_content_of_malformed_returns_empty():
    assert content_of({}) == ""
    assert content_of({"choices": []}) == ""
    assert content_of(None) == ""


# --- needs_sharding ----------------------------------------------------------
def test_needs_sharding_true_when_no_fit():
    assert needs_sharding(Job.new("m", min_vram_mb=10**9), [_node("small", vram=1000)])


def test_needs_sharding_false_when_fits():
    assert not needs_sharding(Job.new("m", min_vram_mb=1000), [_node("big", vram=24000)])


def test_needs_sharding_false_when_no_vram_requirement():
    assert not needs_sharding(Job.new("m", min_vram_mb=0), [])


# --- run_job -----------------------------------------------------------------
def test_run_job_no_runnable_node_errors():
    sc = SwarmController()
    sc.register(_node("no-endpoint", endpoint=""))  # not runnable
    res = run_job(sc, Job.new("m"), {"messages": []}, "buyer")
    assert res["ok"] is False and "no eligible runnable node" in res["error"]


def test_run_job_sharding_hint_when_oversized():
    sc = SwarmController()
    sc.register(_node("small", vram=1000, endpoint="http://x"))
    res = run_job(sc, Job.new("m", min_vram_mb=10**9), {"messages": []}, "buyer")
    assert res["ok"] is False and "sharding-capable" in res["error"]


def test_run_job_success_settles_and_rewards():
    srv, url = _spawn("ok")
    try:
        sc = SwarmController()
        sc.ledger.grant("buyer", 10)
        sc.register(_node("worker", endpoint=url))
        res = run_job(sc, Job.new("m"), {"messages": [{"role": "user", "content": "hi"}]},
                      "buyer", price=2.0)
        assert res["ok"] and res["paid"] == 2.0
        assert sc.ledger.balance("worker") == 2.0 and sc.ledger.balance("buyer") == 8.0
        assert sc.ledger.rep("worker") > 1.0
    finally:
        srv.shutdown()


def test_run_job_unfunded_consumer_runs_but_pays_zero():
    srv, url = _spawn("ok")
    try:
        sc = SwarmController()
        sc.register(_node("worker", endpoint=url))
        res = run_job(sc, Job.new("m"), {"messages": []}, "broke", price=5.0)
        assert res["ok"] and res["paid"] == 0.0  # settle failed, job still ran
    finally:
        srv.shutdown()


def test_run_job_fails_over_to_next_node():
    bad_srv, bad_url = _spawn("fail")
    good_srv, good_url = _spawn("ok")
    try:
        sc = SwarmController()
        sc.ledger.grant("buyer", 10)
        # make the bad node higher reputation so it's tried first
        sc.ledger.reputation["bad"] = 4.0
        sc.ledger.reputation["good"] = 1.0
        sc.register(_node("bad", endpoint=bad_url))
        sc.register(_node("good", endpoint=good_url))
        res = run_job(sc, Job.new("m"), {"messages": []}, "buyer")
        assert res["ok"] and res["node_id"] == "good"
        assert len(res["attempts"]) == 1 and res["attempts"][0]["node_id"] == "bad"
        assert sc.ledger.rep("bad") < 4.0  # failure penalized
    finally:
        bad_srv.shutdown()
        good_srv.shutdown()


def test_run_job_all_nodes_fail():
    srv, url = _spawn("fail")
    try:
        sc = SwarmController()
        sc.register(_node("bad1", endpoint=url))
        res = run_job(sc, Job.new("m"), {"messages": []}, "buyer")
        assert res["ok"] is False and "failed" in res["error"]
    finally:
        srv.shutdown()


# --- scatter_gather ----------------------------------------------------------
def test_scatter_gather_no_nodes():
    sc = SwarmController()
    res = scatter_gather(sc, "m", ["a", "b"])
    assert res["ok"] is False


def test_scatter_gather_all_mode():
    srv, url = _spawn("echo")
    try:
        sc = SwarmController()
        sc.register(_node("w", endpoint=url))
        res = scatter_gather(sc, "m", ["p1", "p2"], aggregate="all")
        assert res["ok"] and res["count"] == 2
        assert all("content" in r for r in res["results"])
    finally:
        srv.shutdown()


def test_scatter_gather_concat_mode():
    srv, url = _spawn("echo")
    try:
        sc = SwarmController()
        sc.register(_node("w", endpoint=url))
        res = scatter_gather(sc, "m", ["x", "y"], aggregate="concat")
        assert "echo:x" in res["result"] and "echo:y" in res["result"]
    finally:
        srv.shutdown()


def test_scatter_gather_first_mode():
    srv, url = _spawn("echo")
    try:
        sc = SwarmController()
        sc.register(_node("w", endpoint=url))
        res = scatter_gather(sc, "m", ["only"], aggregate="first")
        assert res["result"] == "echo:only"
    finally:
        srv.shutdown()


def test_scatter_gather_vote_mode():
    srv, url = _spawn("echo")
    try:
        sc = SwarmController()
        sc.register(_node("w", endpoint=url))
        # all identical prompts -> identical echoes -> a clear majority
        res = scatter_gather(sc, "m", ["same", "same", "same"], aggregate="vote")
        assert res["result"] == "echo:same"
    finally:
        srv.shutdown()


# --- StreamMeter -------------------------------------------------------------
def _sse(obj):
    return b"data: " + json.dumps(obj).encode() + b"\n"


def test_stream_meter_counts_content_deltas():
    m = StreamMeter()
    m.feed(_sse({"choices": [{"delta": {"content": "a"}}]}))
    m.feed(_sse({"choices": [{"delta": {"content": "b"}}]}))
    assert m.tokens == 2


def test_stream_meter_ignores_empty_deltas():
    m = StreamMeter()
    m.feed(_sse({"choices": [{"delta": {}}]}))
    m.feed(_sse({"choices": [{"delta": {"content": ""}}]}))
    assert m.tokens == 0


def test_stream_meter_prefers_explicit_usage():
    m = StreamMeter()
    m.feed(_sse({"choices": [{"delta": {"content": "x"}}]}))
    m.feed(_sse({"choices": [{"delta": {}}], "usage": {"completion_tokens": 99}}))
    assert m.tokens == 99


def test_stream_meter_handles_split_chunks():
    m = StreamMeter()
    line = _sse({"choices": [{"delta": {"content": "z"}}]})
    m.feed(line[:8])
    m.feed(line[8:])
    assert m.tokens == 1


def test_stream_meter_skips_done_and_junk():
    m = StreamMeter()
    m.feed(b"data: [DONE]\n")
    m.feed(b"data: not-json\n")
    m.feed(b": a comment line\n")
    assert m.tokens == 0


# --- metered_stream ----------------------------------------------------------
class _FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False

    def read(self, size):
        return self._chunks.pop(0) if self._chunks else b""

    def close(self):
        self.closed = True


def test_metered_stream_bills_per_token():
    sc = SwarmController()
    sc.ledger.grant("buyer", 100)
    sc.register(_node("w", endpoint="http://x"))
    chunks = [_sse({"choices": [{"delta": {"content": "a"}}]}),
              _sse({"choices": [{"delta": {"content": "b"}}]})]
    out = list(metered_stream(_FakeStream(chunks), sc, "w", "buyer", 0.5))
    assert out  # chunks relayed
    assert sc.ledger.balance("w") == 1.0  # 2 tokens * 0.5


def test_metered_stream_min_charge():
    sc = SwarmController()
    sc.ledger.grant("buyer", 100)
    sc.register(_node("w", endpoint="http://x"))
    list(metered_stream(_FakeStream([b""]), sc, "w", "buyer", 0.001, min_charge=3.0))
    assert sc.ledger.balance("w") == 3.0  # no tokens, but min_charge applies
