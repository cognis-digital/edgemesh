"""Edge cases and error paths for the scheduler: privacy gate, VRAM fit,
sharding exemption, auction scoring/ordering, and failover ranking."""

from __future__ import annotations

from edgemesh.ledger import Ledger
from edgemesh.protocol import (CLASS_A, CLASS_B, CLASS_C, DATA_CONFIDENTIAL,
                               DATA_PRIVATE, DATA_PUBLIC, HardwareProfile, Job,
                               NodeInfo)
from edgemesh.scheduler import allowed_classes, eligible, ranked, schedule


def _node(nid, node_class=CLASS_C, vram=8000, accel="cuda", ram=32000,
          sharding=False, endpoint=""):
    return NodeInfo(node_id=nid, name=nid, node_class=node_class, endpoint=endpoint,
                    profile=HardwareProfile(os="Linux", arch="x86_64", accelerator=accel,
                                            ram_mb=ram, vram_mb=vram, gpu_name="GPU"),
                    sharding=sharding)


# --- allowed_classes ---------------------------------------------------------
def test_allowed_classes_confidential():
    assert allowed_classes(DATA_CONFIDENTIAL) == {CLASS_A}


def test_allowed_classes_private():
    assert allowed_classes(DATA_PRIVATE) == {CLASS_A, CLASS_B}


def test_allowed_classes_public_is_all():
    assert allowed_classes(DATA_PUBLIC) == {CLASS_A, CLASS_B, CLASS_C}


def test_allowed_classes_unknown_defaults_to_all():
    assert allowed_classes("garbage") == {CLASS_A, CLASS_B, CLASS_C}


# --- eligible: privacy gate --------------------------------------------------
def test_eligible_confidential_only_class_a():
    nodes = [_node("a", CLASS_A), _node("b", CLASS_B), _node("c", CLASS_C)]
    got = eligible(Job.new("m", data_class=DATA_CONFIDENTIAL), nodes)
    assert {n.node_id for n in got} == {"a"}


def test_eligible_private_excludes_class_c():
    nodes = [_node("a", CLASS_A), _node("b", CLASS_B), _node("c", CLASS_C)]
    got = eligible(Job.new("m", data_class=DATA_PRIVATE), nodes)
    assert {n.node_id for n in got} == {"a", "b"}


def test_eligible_public_allows_all_classes():
    nodes = [_node("a", CLASS_A), _node("b", CLASS_B), _node("c", CLASS_C)]
    got = eligible(Job.new("m", data_class=DATA_PUBLIC), nodes)
    assert {n.node_id for n in got} == {"a", "b", "c"}


def test_eligible_empty_node_list():
    assert eligible(Job.new("m"), []) == []


# --- eligible: VRAM fit ------------------------------------------------------
def test_eligible_vram_filter_excludes_too_small():
    nodes = [_node("small", vram=2000), _node("big", vram=24000)]
    got = eligible(Job.new("m", min_vram_mb=16000), nodes)
    assert {n.node_id for n in got} == {"big"}


def test_eligible_zero_min_vram_skips_filter():
    n = _node("nogpu", accel="cpu", vram=None, ram=None)
    assert [x.node_id for x in eligible(Job.new("m", min_vram_mb=0), [n])] == ["nogpu"]


def test_eligible_node_with_unknown_vram_excluded_when_min_required():
    n = _node("unknown", accel="cpu", vram=None, ram=None)
    assert eligible(Job.new("m", min_vram_mb=1), [n]) == []


def test_eligible_vram_exact_boundary_included():
    # usable_vram for cuda == vram_mb; a job needing exactly that fits.
    n = _node("edge", accel="cuda", vram=8000)
    assert [x.node_id for x in eligible(Job.new("m", min_vram_mb=8000), [n])] == ["edge"]


def test_eligible_cpu_node_uses_60pct_of_ram():
    # cpu usable_vram = ram*0.60 -> 16000*0.6 = 9600
    n = _node("cpu", accel="cpu", vram=None, ram=16000)
    assert eligible(Job.new("m", min_vram_mb=9600), [n])
    assert eligible(Job.new("m", min_vram_mb=9601), [n]) == []


def test_eligible_mlx_node_uses_70pct_of_ram():
    n = _node("mac", accel="mlx", vram=None, ram=100000)  # usable 70000
    assert eligible(Job.new("m", min_vram_mb=70000), [n])
    assert eligible(Job.new("m", min_vram_mb=70001), [n]) == []


# --- eligible: sharding exemption --------------------------------------------
def test_sharding_node_exempt_from_vram_filter():
    n = _node("shard", accel="mlx", vram=None, ram=8000, sharding=True)
    # tiny node, but sharding -> exempt from the single-node VRAM filter
    assert [x.node_id for x in eligible(Job.new("m", min_vram_mb=999999), [n])] == ["shard"]


def test_sharding_node_still_bound_by_privacy():
    # sharding exempts VRAM only, NOT the privacy gate
    n = _node("shard", CLASS_C, sharding=True)
    assert eligible(Job.new("m", data_class=DATA_CONFIDENTIAL, min_vram_mb=999999), [n]) == []


# --- ranked / auction --------------------------------------------------------
def test_ranked_prefers_higher_reputation():
    led = Ledger()
    led.reputation["good"] = 3.0
    led.reputation["meh"] = 1.0
    order = ranked(Job.new("m"), [_node("meh"), _node("good")], led, price=1.0)
    assert [n.node_id for n in order] == ["good", "meh"]


def test_ranked_prefers_cheaper_when_reputation_equal():
    # price is uniform in ranked(); score = rep/price so a single-fit node beats sharding
    led = Ledger()
    order = ranked(Job.new("m"), [_node("single"), _node("shard", sharding=True)], led)
    assert order[0].node_id == "single"  # sharding penalized 0.75x


def test_ranked_empty_when_no_eligible():
    assert ranked(Job.new("m", min_vram_mb=10**9), [_node("x", vram=1000)]) == []


def test_ranked_default_ledger_when_none_passed():
    order = ranked(Job.new("m"), [_node("a"), _node("b")])
    assert len(order) == 2  # all start at reputation 1.0, both eligible


def test_score_guards_against_zero_price():
    # price clamped to >=0.01 so no ZeroDivisionError
    led = Ledger()
    order = ranked(Job.new("m"), [_node("a")], led, price=0.0)
    assert order[0].node_id == "a"


# --- schedule ----------------------------------------------------------------
def test_schedule_returns_assignment_for_best_node():
    led = Ledger()
    led.reputation["win"] = 4.0
    a = schedule(Job.new("m"), [_node("lose"), _node("win")], led)
    assert a is not None and a.node_id == "win"


def test_schedule_none_when_no_eligible():
    assert schedule(Job.new("m", min_vram_mb=10**9), [_node("x", vram=100)]) is None


def test_schedule_carries_price_into_assignment():
    a = schedule(Job.new("j"), [_node("a")], Ledger(), price=3.5)
    assert a.price == 3.5 and a.job_id == a.job_id
