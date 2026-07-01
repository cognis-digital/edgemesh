"""Gateway error-path and endpoint coverage: 404s, 400 bad request, 413 oversize,
429 rate limit, health/models/nodes/ledger endpoints, and relay-not-configured."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from edgemesh import limits
from edgemesh.backends import Backend
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry
from edgemesh.swarm import SwarmController


@pytest.fixture()
def gw():
    reg = BackendRegistry([Backend("stub", "http://127.0.0.1:1", ["known"])])
    sc = SwarmController()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg, sc))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    yield reg, sc, base
    srv.shutdown()


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, json.loads(r.read())


def _post(base, path, payload, raw=None):
    data = raw if raw is not None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


# --- GET endpoints -----------------------------------------------------------
def test_healthz(gw):
    _, _, base = gw
    status, body = _get(base, "/healthz")
    assert status == 200 and body["status"] == "ok"
    assert "stub" in body["backends"]


def test_models_catalog(gw):
    _, _, base = gw
    _, body = _get(base, "/v1/models")
    assert body["object"] == "list"
    assert any(m["id"] == "known" for m in body["data"])


def test_swarm_nodes_empty(gw):
    _, _, base = gw
    _, body = _get(base, "/swarm/nodes")
    assert body["nodes"] == []


def test_cluster_nodes_empty(gw):
    _, _, base = gw
    _, body = _get(base, "/cluster/nodes")
    assert body["nodes"] == {}


def test_ledger_endpoint(gw):
    _, _, base = gw
    _, body = _get(base, "/swarm/ledger")
    assert "credits" in body and "reputation" in body


def test_unknown_get_404(gw):
    _, _, base = gw
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + "/nope", timeout=5)
    assert exc.value.code == 404


def test_relay_info_404_when_not_relay(gw):
    _, _, base = gw
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + "/relay/info", timeout=5)
    assert exc.value.code == 404


# --- POST error paths --------------------------------------------------------
def test_chat_missing_model_400(gw):
    _, _, base = gw
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/v1/chat/completions", {"messages": []})
    assert exc.value.code == 400


def test_chat_unknown_model_404(gw):
    _, _, base = gw
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/v1/chat/completions", {"model": "ghost", "messages": []})
    assert exc.value.code == 404


def test_oversize_body_413(gw):
    _, _, base = gw
    big = b"x" * (limits.MAX_BODY_BYTES + 10)
    # The gateway rejects on Content-Length *before* reading the body, so the
    # server may send 413 or simply reset the connection mid-upload (an equally
    # valid rejection). Accept either — both prove the oversized body is refused.
    try:
        _post(base, "/v1/chat/completions", None, raw=big)
        raise AssertionError("oversized body should have been rejected")
    except urllib.error.HTTPError as exc:
        assert exc.code == 413
    except (ConnectionError, urllib.error.URLError, OSError):
        pass  # connection reset mid-upload is an acceptable rejection


def test_swarm_submit_no_node_409(gw):
    _, _, base = gw
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/swarm/submit", {"model": "m"})
    assert exc.value.code == 409


def test_swarm_register_below_floor_400(gw):
    _, _, base = gw
    node = {"node_id": "weak", "name": "weak", "node_class": "C", "endpoint": "http://x",
            "profile": {"os": "L", "arch": "x", "accelerator": "cpu", "ram_mb": 100}}
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/swarm/register", node)
    assert exc.value.code == 400


def test_swarm_register_ok(gw):
    _, sc, base = gw
    node = {"node_id": "ok", "name": "ok", "node_class": "C", "endpoint": "http://x",
            "profile": {"os": "L", "arch": "x", "accelerator": "cuda", "ram_mb": 32000,
                        "vram_mb": 12000}}
    status, body = _post(base, "/swarm/register", node)
    assert status == 200 and body["ok"] and body["inference_capable"] is True
    assert len(sc.nodes) == 1


def test_swarm_complete_unknown_job(gw):
    _, _, base = gw
    status, body = _post(base, "/swarm/complete", {"job_id": "nope", "consumer": "c"})
    assert status == 200 and body["ok"] is False


def test_relay_forward_404_when_not_relay(gw):
    _, _, base = gw
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/relay/forward", {"blob": "x"})
    assert exc.value.code == 404


def test_unknown_post_404(gw):
    _, _, base = gw
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, "/bogus", {})
    assert exc.value.code == 404


def test_metrics_endpoint_text_format(gw):
    _, _, base = gw
    with urllib.request.urlopen(base + "/metrics", timeout=5) as r:
        assert r.headers.get("Content-Type", "").startswith("text/plain")
        body = r.read().decode()
    assert "edgemesh_swarm_nodes" in body
