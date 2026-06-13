"""Prometheus metrics: counter/gauge rendering + the /metrics endpoint."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from edgemesh.gateway import make_handler
from edgemesh.metrics import Metrics
from edgemesh.registry import BackendRegistry
from edgemesh.swarm import SwarmController


def test_render_counters_and_gauges():
    m = Metrics()
    m.inc("edgemesh_requests_total", {"route": "/swarm/run"})
    m.inc("edgemesh_requests_total", {"route": "/swarm/run"})
    out = m.render({"edgemesh_backends": 3.0})
    assert '# TYPE edgemesh_requests_total counter' in out
    assert 'edgemesh_requests_total{route="/swarm/run"} 2.0' in out
    assert '# TYPE edgemesh_backends gauge' in out and 'edgemesh_backends 3.0' in out


def test_metrics_endpoint_e2e():
    m = Metrics()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(BackendRegistry(), SwarmController(), metrics=m))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        # a request bumps the counter
        try:
            urllib.request.urlopen(urllib.request.Request(
                base + "/swarm/submit", data=json.dumps({"model": "m"}).encode(),
                headers={"Content-Type": "application/json"}, method="POST"), timeout=5)
        except Exception:
            pass  # 409 no node is fine; we only care the counter incremented
        with urllib.request.urlopen(base + "/metrics", timeout=5) as r:
            assert r.headers.get("Content-Type", "").startswith("text/plain")
            body = r.read().decode()
        assert "edgemesh_requests_total" in body
        assert "edgemesh_swarm_nodes" in body  # live gauge present
    finally:
        srv.shutdown()
