"""Streaming (SSE): executor.stream_job relays + settles, and the gateway relays
an upstream event-stream verbatim. Exercised against a mock SSE backend."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from edgemesh.backends import Backend
from edgemesh.executor import iter_chunks, stream_job
from edgemesh.gateway import make_handler
from edgemesh.protocol import CLASS_C, HardwareProfile, Job, NodeInfo
from edgemesh.registry import BackendRegistry
from edgemesh.swarm import SwarmController

SSE_BODY = (b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
            b'data: [DONE]\n\n')


class _SSEBackend(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(SSE_BODY)))
        self.end_headers()
        self.wfile.write(SSE_BODY)


@pytest.fixture()
def sse():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _SSEBackend)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _node(nid, endpoint):
    return NodeInfo(node_id=nid, name=nid, node_class=CLASS_C, endpoint=endpoint,
                    profile=HardwareProfile(os="Linux", arch="x86_64", accelerator="cuda",
                                            ram_mb=32000, vram_mb=12000, gpu_name="GPU"))


def test_stream_job_relays_and_settles(sse):
    sc = SwarmController()
    sc.ledger.grant("buyer", 5)
    sc.register(_node("n1", sse))
    nid, resp, attempts = stream_job(sc, Job.new("m"),
                                     {"messages": [{"role": "user", "content": "hi"}]},
                                     "buyer", price=2.0)
    assert nid == "n1" and resp is not None
    data = b"".join(iter_chunks(resp))
    assert b"Hel" in data and b"lo" in data and b"[DONE]" in data
    assert sc.ledger.balance("n1") == 2.0 and sc.ledger.balance("buyer") == 3.0


def test_gateway_v1_streaming_relay(sse):
    reg = BackendRegistry()
    reg.add(Backend(name="b", base_url=sse, models=["m"]))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    try:
        req = urllib.request.Request(
            base + "/v1/chat/completions",
            data=json.dumps({"model": "m", "stream": True, "messages": []}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.headers.get("Content-Type") == "text/event-stream"
            body = r.read()
        assert b"[DONE]" in body and b"Hel" in body
    finally:
        server.shutdown()
