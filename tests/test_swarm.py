"""Tests for the swarm control plane folded into edgemesh: protocol tokens,
ledger, scheduler (privacy + fit + auction), SwarmController, and the gateway's
/swarm endpoints end-to-end over a real socket."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from edgemesh.gateway import make_handler
from edgemesh.ledger import MAX_REPUTATION, MIN_REPUTATION, Ledger
from edgemesh.protocol import (CLASS_A, CLASS_B, CLASS_C, DATA_CONFIDENTIAL,
                               DATA_PRIVATE, HardwareProfile, Job, NodeInfo,
                               issue_token, verify_token)
from edgemesh.registry import BackendRegistry
from edgemesh.scheduler import eligible, schedule
from edgemesh.swarm import SwarmController


def _node(nid, node_class=CLASS_C, vram=8000, accel="cuda"):
    return NodeInfo(node_id=nid, name=nid, node_class=node_class, endpoint="",
                    profile=HardwareProfile(os="Linux", arch="x86_64", accelerator=accel,
                                            ram_mb=32000, vram_mb=vram, gpu_name="GPU"))


# --- protocol tokens ---------------------------------------------------------
def test_token_roundtrip_and_tamper():
    import base64
    t = issue_token("secret", "node-1", ttl_s=60)
    assert verify_token("secret", t) == "node-1"
    assert verify_token("wrong-secret", t) is None
    # tamper the signed payload (swap the node id) without re-signing -> must fail
    raw = base64.urlsafe_b64decode(t).decode()
    nid, expiry, sig = raw.split("|")
    forged = base64.urlsafe_b64encode(f"node-2|{expiry}|{sig}".encode()).decode()
    assert verify_token("secret", forged) is None
    assert verify_token("secret", "not-valid-base64!!") is None


def test_token_expiry():
    assert verify_token("s", issue_token("s", "n", ttl_s=-1)) is None


# --- ledger ------------------------------------------------------------------
def test_settle_moves_credits_and_blocks_overdraw():
    led = Ledger()
    led.grant("consumer", 10)
    assert led.settle("consumer", "node", 4) is True
    assert led.balance("consumer") == 6 and led.balance("node") == 4
    assert led.settle("consumer", "node", 100) is False  # insufficient


def test_reputation_bounds():
    led = Ledger()
    for _ in range(50):
        led.record_outcome("n", success=False)
    assert led.rep("n") >= MIN_REPUTATION
    for _ in range(200):
        led.record_outcome("n", success=True)
    assert led.rep("n") <= MAX_REPUTATION


# --- scheduler (privacy + fit + auction) -------------------------------------
def test_privacy_gate_confidential_is_class_a_only():
    nodes = [_node("a", CLASS_A), _node("b", CLASS_B), _node("c", CLASS_C)]
    job = Job.new("m", data_class=DATA_CONFIDENTIAL)
    assert {n.node_id for n in eligible(job, nodes)} == {"a"}
    job2 = Job.new("m", data_class=DATA_PRIVATE)
    assert {n.node_id for n in eligible(job2, nodes)} == {"a", "b"}


def test_capability_filter_vram():
    nodes = [_node("small", vram=2000), _node("big", vram=24000)]
    job = Job.new("m", min_vram_mb=16000)
    assert {n.node_id for n in eligible(job, nodes)} == {"big"}


def test_auction_prefers_higher_reputation():
    led = Ledger()
    led.reputation["good"] = 3.0
    led.reputation["meh"] = 1.0
    nodes = [_node("good"), _node("meh")]
    a = schedule(Job.new("m"), nodes, led, price=1.0)
    assert a.node_id == "good"


def test_schedule_none_when_no_eligible():
    assert schedule(Job.new("m", min_vram_mb=999999), [_node("x", vram=1000)]) is None


# --- SwarmController ----------------------------------------------------------
def test_register_submit_complete_flow():
    sc = SwarmController()
    sc.ledger.grant("buyer", 10)
    sc.register(_node("worker", CLASS_C, vram=12000), now=1000.0)
    a = sc.submit(Job.new("llama", min_vram_mb=6000), price=2.0)
    assert a and a.node_id == "worker"
    res = sc.complete(a.job_id, "buyer", success=True)
    assert res["ok"] and res["paid"] == 2.0
    assert sc.ledger.balance("worker") == 2.0 and sc.ledger.balance("buyer") == 8.0
    assert sc.ledger.rep("worker") > 1.0  # success bumped reputation


def test_prune_drops_stale():
    sc = SwarmController()
    sc.register(_node("old"), now=0.0)
    sc.register(_node("new"), now=1000.0)
    dropped = sc.prune(ttl_s=120.0, now=1000.0)
    assert dropped == ["old"] and "new" in sc.nodes


# --- gateway /swarm end-to-end -----------------------------------------------
@pytest.fixture()
def gw():
    reg = BackendRegistry()
    sc = SwarmController()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg, sc))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield sc, "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_swarm_endpoints_e2e(gw):
    sc, base = gw
    node = _node("e2e-1", CLASS_C, vram=10000)
    reg = _post(base + "/swarm/register", node.to_dict())
    assert reg["ok"] and reg["swarm_size"] == 1
    sub = _post(base + "/swarm/submit", {"model": "llama", "min_vram_mb": 6000, "price": 1.5})
    assert sub["node_id"] == "e2e-1"
    with urllib.request.urlopen(base + "/swarm/nodes", timeout=5) as r:
        assert len(json.loads(r.read())["nodes"]) == 1
