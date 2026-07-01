"""Protocol edge cases: HMAC tokens, dataclass (de)serialization, Job.new defaults."""

from __future__ import annotations

import base64
import time

from edgemesh.protocol import (CLASS_A, CLASS_C, DATA_PUBLIC, PROTOCOL_VERSION,
                               Assignment, HardwareProfile, Job, NodeInfo, dumps,
                               issue_token, verify_token)


# --- tokens ------------------------------------------------------------------
def test_token_roundtrip():
    t = issue_token("secret", "node-1", ttl_s=60)
    assert verify_token("secret", t) == "node-1"


def test_token_wrong_secret():
    t = issue_token("secret", "n", ttl_s=60)
    assert verify_token("other", t) is None


def test_token_expired():
    assert verify_token("s", issue_token("s", "n", ttl_s=-1)) is None


def test_token_garbage_input():
    assert verify_token("s", "!!!not-base64!!!") is None
    assert verify_token("s", "") is None


def test_token_tamper_node_id():
    t = issue_token("secret", "node-1", ttl_s=60)
    raw = base64.urlsafe_b64decode(t).decode()
    nid, expiry, sig = raw.split("|")
    forged = base64.urlsafe_b64encode(f"node-2|{expiry}|{sig}".encode()).decode()
    assert verify_token("secret", forged) is None


def test_token_tamper_expiry_extends_life_but_breaks_sig():
    t = issue_token("secret", "n", ttl_s=1)
    raw = base64.urlsafe_b64decode(t).decode()
    nid, expiry, sig = raw.split("|")
    future = str(int(time.time()) + 9999)
    forged = base64.urlsafe_b64encode(f"{nid}|{future}|{sig}".encode()).decode()
    assert verify_token("secret", forged) is None  # sig no longer matches


def test_token_uses_constant_time_compare():
    # sanity: a valid token still verifies (compare_digest path)
    t = issue_token("k", "abc", ttl_s=30)
    assert verify_token("k", t) == "abc"


# --- HardwareProfile ---------------------------------------------------------
def test_profile_optional_telemetry_defaults_none():
    p = HardwareProfile(os="L", arch="x", accelerator="cpu")
    assert p.bandwidth_mbps is None and p.battery_pct is None


# --- NodeInfo (de)serialization ----------------------------------------------
def test_nodeinfo_to_from_dict_roundtrip():
    n = NodeInfo("id", "name", CLASS_A, "http://x",
                 HardwareProfile(os="L", arch="x", accelerator="cuda", vram_mb=8000),
                 sharding=True)
    d = n.to_dict()
    back = NodeInfo.from_dict(d)
    assert back.node_id == "id" and back.sharding is True
    assert back.profile.vram_mb == 8000


def test_nodeinfo_from_dict_defaults():
    n = NodeInfo.from_dict({"node_id": "x"})
    assert n.node_class == CLASS_C and n.reputation == 1.0 and n.sharding is False


def test_nodeinfo_from_dict_accepts_profile_object():
    prof = HardwareProfile(os="L", arch="x", accelerator="cpu", ram_mb=16000)
    n = NodeInfo.from_dict({"node_id": "x", "profile": prof})
    assert n.profile is prof


def test_nodeinfo_from_dict_coerces_numeric_types():
    n = NodeInfo.from_dict({"node_id": "x", "reputation": "2.5", "last_seen": "100"})
    assert n.reputation == 2.5 and n.last_seen == 100.0


# --- Job ---------------------------------------------------------------------
def test_job_new_defaults():
    j = Job.new("model-x")
    assert j.model == "model-x" and j.data_class == DATA_PUBLIC
    assert j.min_vram_mb == 0 and len(j.job_id) == 12


def test_job_new_unique_ids():
    assert Job.new("m").job_id != Job.new("m").job_id


def test_job_new_passes_kwargs():
    j = Job.new("m", data_class="private", min_vram_mb=4000, submitted_by="acme")
    assert j.data_class == "private" and j.min_vram_mb == 4000 and j.submitted_by == "acme"


# --- Assignment / dumps ------------------------------------------------------
def test_assignment_default_shards_empty():
    a = Assignment(job_id="j", node_id="n", price=1.0)
    assert a.shards == []


def test_dumps_serializes_dataclass():
    j = Job.new("m")
    raw = dumps(j)
    assert b"job_id" in raw and b"model" in raw


def test_protocol_version_present():
    assert PROTOCOL_VERSION
