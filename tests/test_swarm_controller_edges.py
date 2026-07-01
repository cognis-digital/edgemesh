"""SwarmController lifecycle edge cases: register/heartbeat/prune, submit/complete
settlement, failed-job reputation, and node-class listing."""

from __future__ import annotations

from edgemesh.ledger import Ledger
from edgemesh.protocol import (CLASS_A, CLASS_B, CLASS_C, HardwareProfile, Job,
                               NodeInfo)
from edgemesh.swarm import SwarmController


def _node(nid, node_class=CLASS_C, vram=8000):
    return NodeInfo(node_id=nid, name=nid, node_class=node_class, endpoint="",
                    profile=HardwareProfile(os="L", arch="x", accelerator="cuda",
                                            ram_mb=32000, vram_mb=vram, gpu_name="G"))


def test_register_sets_last_seen_and_reputation():
    sc = SwarmController()
    n = sc.register(_node("a"), now=123.0)
    assert n.last_seen == 123.0 and n.reputation == sc.ledger.rep("a")


def test_register_reflects_existing_reputation():
    led = Ledger()
    led.reputation["veteran"] = 3.5
    sc = SwarmController(led)
    n = sc.register(_node("veteran"))
    assert n.reputation == 3.5


def test_heartbeat_updates_last_seen():
    sc = SwarmController()
    sc.register(_node("a"), now=0.0)
    assert sc.heartbeat("a", now=50.0) is True
    assert sc.nodes["a"].last_seen == 50.0


def test_heartbeat_unknown_node_false():
    assert SwarmController().heartbeat("ghost") is False


def test_prune_drops_only_stale():
    sc = SwarmController()
    sc.register(_node("old"), now=0.0)
    sc.register(_node("fresh"), now=1000.0)
    dropped = sc.prune(ttl_s=120.0, now=1000.0)
    assert dropped == ["old"] and "fresh" in sc.nodes


def test_prune_nothing_when_all_fresh():
    sc = SwarmController()
    sc.register(_node("a"), now=1000.0)
    assert sc.prune(ttl_s=120.0, now=1000.0) == []


def test_list_nodes_filter_by_class():
    sc = SwarmController()
    sc.register(_node("a", CLASS_A))
    sc.register(_node("b", CLASS_B))
    sc.register(_node("c", CLASS_C))
    assert [n.node_id for n in sc.list_nodes(CLASS_A)] == ["a"]
    assert len(sc.list_nodes()) == 3


def test_submit_returns_none_when_no_eligible():
    sc = SwarmController()
    sc.register(_node("small", vram=1000))
    assert sc.submit(Job.new("m", min_vram_mb=10**9)) is None


def test_submit_records_assignment():
    sc = SwarmController()
    sc.register(_node("a", vram=12000))
    a = sc.submit(Job.new("m", min_vram_mb=6000), price=2.0)
    assert a is not None and a.node_id == "a"
    assert sc._assignments[a.job_id] is a


def test_complete_success_pays_and_rewards():
    sc = SwarmController()
    sc.ledger.grant("buyer", 10)
    sc.register(_node("worker", vram=12000))
    a = sc.submit(Job.new("m", min_vram_mb=6000), price=3.0)
    res = sc.complete(a.job_id, "buyer", success=True)
    assert res["ok"] and res["paid"] == 3.0
    assert sc.ledger.balance("worker") == 3.0
    assert sc.nodes["worker"].reputation > 1.0


def test_complete_failure_penalizes_no_payment():
    sc = SwarmController()
    sc.ledger.grant("buyer", 10)
    sc.register(_node("worker", vram=12000))
    a = sc.submit(Job.new("m", min_vram_mb=6000), price=3.0)
    res = sc.complete(a.job_id, "buyer", success=False)
    assert res["ok"] and res["paid"] == 0.0
    assert sc.ledger.balance("worker") == 0.0
    assert sc.nodes["worker"].reputation < 1.0


def test_complete_unknown_job():
    assert SwarmController().complete("nope", "c")["ok"] is False


def test_complete_success_but_unfunded_pays_zero():
    sc = SwarmController()
    sc.register(_node("worker", vram=12000))
    a = sc.submit(Job.new("m", min_vram_mb=6000), price=5.0)
    res = sc.complete(a.job_id, "broke", success=True)
    # settle failed (no funds) so paid=0; reputation reflects settled==False
    assert res["paid"] == 0.0


def test_complete_is_idempotent_guarded():
    sc = SwarmController()
    sc.ledger.grant("buyer", 10)
    sc.register(_node("worker", vram=12000))
    a = sc.submit(Job.new("m", min_vram_mb=6000), price=2.0)
    sc.complete(a.job_id, "buyer", success=True)
    # second complete of the same job: assignment already popped -> unknown
    assert sc.complete(a.job_id, "buyer", success=True)["ok"] is False
