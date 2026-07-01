"""Coverage for cluster join/register, VSCode/MCP integrations, sharding presets,
signed relay directory, metrics store, and audit log."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from edgemesh import cluster, integrations, presets, relay
from edgemesh.audit import AuditLog
from edgemesh.backends import Backend
from edgemesh.gateway import make_handler
from edgemesh.metrics import Metrics
from edgemesh.registry import BackendRegistry


# --- cluster -----------------------------------------------------------------
def test_local_ip_returns_string():
    ip = cluster.local_ip()
    assert isinstance(ip, str) and ip.count(".") == 3


def test_readvertise_rewrites_localhost():
    b = Backend("ollama", "http://127.0.0.1:11434", ["m"])
    out = cluster._readvertise(b, "10.0.0.5")
    assert out.base_url == "http://10.0.0.5:11434" and out.models == ["m"]


def test_readvertise_leaves_real_host():
    b = Backend("x", "http://192.168.1.9:8000", ["m"])
    assert cluster._readvertise(b, "10.0.0.5").base_url == "http://192.168.1.9:8000"


def test_register_into_merges_backends():
    reg = BackendRegistry()
    added = cluster.register_into(reg, {"backends": [
        {"name": "node.ollama", "base_url": "http://10.0.0.5:11434", "models": ["m"]}]})
    assert added == ["node.ollama"] and reg.get("node.ollama").models == ["m"]


def test_register_into_skips_malformed():
    reg = BackendRegistry()
    added = cluster.register_into(reg, {"backends": [{"bad": "entry"}, {"name": "ok",
                                  "base_url": "http://h:1", "models": []}]})
    assert added == ["ok"]


def test_register_into_empty_payload():
    assert cluster.register_into(BackendRegistry(), {}) == []


def test_join_registers_with_coordinator():
    # stand up a coordinator gateway, then join with no local backends discovered
    reg = BackendRegistry()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        # discover_local will probe dead ports and find nothing -> empty registration
        resp = cluster.join(base, node_name="tester", advertise_host="10.0.0.9")
        assert resp["ok"] and resp["node"] == "tester"
    finally:
        srv.shutdown()


# --- integrations ------------------------------------------------------------
def test_vscode_configs_have_expected_files():
    cfgs = integrations.vscode_configs("my-model")
    assert ".vscode/mcp.json" in cfgs and ".mcp.json" in cfgs
    assert ".continue/config.json" in cfgs


def test_vscode_configs_valid_json():
    for blob in integrations.vscode_configs("m").values():
        json.loads(blob)  # must parse


def test_vscode_continue_uses_gateway_v1():
    cfg = json.loads(integrations.vscode_configs("m")[".continue/config.json"])
    assert cfg["models"][0]["apiBase"].endswith("/v1")
    assert cfg["models"][0]["model"] == "m"


def test_write_vscode_configs(tmp_path):
    written = integrations.write_vscode_configs(Path(tmp_path), "gpt")
    assert written and all(Path(p).exists() for p in written)
    # informational cline file is not written to disk
    assert not any("cline-settings" in p for p in written)


def test_vscode_default_model_placeholder():
    cfgs = integrations.vscode_configs()
    assert "<your-model-id>" in cfgs[".continue/config.json"]


# --- presets -----------------------------------------------------------------
def test_presets_keys_nonempty():
    assert presets.keys() and "exo" in presets.keys()


def test_presets_get_known():
    p = presets.get("exo")
    assert p is not None and p.default_url.endswith("/v1")


def test_presets_get_unknown_none():
    assert presets.get("nope") is None


def test_preset_to_dict_shape():
    d = presets.get("vllm-ray").to_dict()
    assert set(d) == {"key", "title", "default_url", "multi_machine", "start_hint", "docs_url"}


def test_presets_have_multi_machine_flag():
    # exo/vllm-ray span machines; tgi/nim are single-node multi-GPU
    assert presets.get("exo").multi_machine is True
    assert presets.get("tgi").multi_machine is False


def test_all_presets_have_docs_url():
    assert all(presets.get(k).docs_url.startswith("http") for k in presets.keys())


# --- metrics -----------------------------------------------------------------
def test_metrics_counter_accumulates():
    m = Metrics()
    m.inc("reqs", {"route": "/x"})
    m.inc("reqs", {"route": "/x"}, n=2.0)
    out = m.render()
    assert 'reqs{route="/x"} 3.0' in out


def test_metrics_no_labels():
    m = Metrics()
    m.inc("bare")
    assert "bare 1.0" in m.render()


def test_metrics_renders_gauges():
    out = Metrics().render({"g": 5.0})
    assert "# TYPE g gauge" in out and "g 5.0" in out


def test_metrics_type_line_once_per_counter():
    m = Metrics()
    m.inc("c", {"a": "1"})
    m.inc("c", {"a": "2"})
    out = m.render()
    assert out.count("# TYPE c counter") == 1


# --- audit -------------------------------------------------------------------
def test_audit_record_and_tail(tmp_path):
    log = AuditLog(str(tmp_path / "audit.log"))
    log.record("submit", principal="alice", model="m", outcome="accepted")
    log.record("run", principal="bob", outcome="denied")
    events = log.tail()
    assert len(events) == 2 and events[-1]["principal"] == "bob"


def test_audit_tail_missing_file(tmp_path):
    assert AuditLog(str(tmp_path / "none.log")).tail() == []


def test_audit_never_logs_content(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    ev = log.record("run", principal="p", model="m", extra={"tokens": 5})
    assert "content" not in ev and "messages" not in ev
    assert ev["tokens"] == 5


def test_audit_tail_limit(tmp_path):
    log = AuditLog(str(tmp_path / "a.log"))
    for i in range(10):
        log.record("act", principal=str(i))
    assert len(log.tail(n=3)) == 3


# --- signed relay directory --------------------------------------------------
crypto = pytest.mark.skipif(not relay.HAVE_CRYPTO, reason="cryptography not installed")


@crypto
def test_directory_accepts_valid():
    from edgemesh import relay_dir
    apriv, apub = relay_dir.gen_authority()
    d = relay_dir.RelayDirectory(apub)
    _, pub = relay.gen_keypair()
    d.add({"relay_id": "r1", "endpoint": "http://10.0.0.1:8780", "public_key": pub}, apriv)
    assert d.verified_relays() == [("http://10.0.0.1:8780", pub)]


@crypto
def test_directory_rejects_tampered():
    from edgemesh import relay_dir
    apriv, apub = relay_dir.gen_authority()
    d = relay_dir.RelayDirectory(apub)
    _, pub = relay.gen_keypair()
    d.add({"relay_id": "r1", "endpoint": "http://a:8780", "public_key": pub}, apriv)
    d.entries[0]["descriptor"]["endpoint"] = "http://evil:8780"
    assert d.verified_relays() == []


@crypto
def test_directory_rejects_wrong_authority():
    from edgemesh import relay_dir
    apriv, _ = relay_dir.gen_authority()
    _, other_pub = relay_dir.gen_authority()
    d = relay_dir.RelayDirectory(other_pub)
    d.add({"relay_id": "r", "endpoint": "http://x", "public_key": "ab"}, apriv)
    assert d.verified_relays() == []


@crypto
def test_directory_json_roundtrip():
    from edgemesh import relay_dir
    apriv, apub = relay_dir.gen_authority()
    d = relay_dir.RelayDirectory(apub)
    _, pub = relay.gen_keypair()
    d.add({"relay_id": "r", "endpoint": "http://x:8780", "public_key": pub}, apriv)
    d2 = relay_dir.RelayDirectory.from_json(d.to_json())
    assert d2.verified_relays() == d.verified_relays()


@crypto
def test_directory_fails_closed_without_crypto(monkeypatch):
    from edgemesh import relay_dir
    monkeypatch.setattr(relay_dir, "HAVE_CRYPTO", False)
    with pytest.raises(relay.RelayUnavailable):
        relay_dir._require()
