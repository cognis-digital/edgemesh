"""Tests for the v0.2 expansion: catalog/fit, hardware, manager, cluster, and
the gateway's cluster-register endpoint (end-to-end over a real socket)."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from edgemesh import catalog, hardware, manager
from edgemesh.backends import Backend
from edgemesh.cluster import _readvertise, register_into
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry


# --- catalog -----------------------------------------------------------------
def test_fit_respects_vram_budget():
    small = catalog.fit(4000)            # 4 GB
    assert all(c.approx_vram_mb <= 4000 * 0.90 for c in small)
    assert any(c.id == "llama3.2-1b" for c in small)
    assert not any(c.id == "llama3.3-70b" for c in small)


def test_fit_none_returns_everything_sorted_desc():
    everything = catalog.fit(None)
    assert len(everything) == len(catalog.CATALOG)
    vrams = [c.approx_vram_mb for c in everything]
    assert vrams == sorted(vrams, reverse=True)


def test_fit_uncensored_toggle():
    with_unc = catalog.fit(None, include_uncensored=True)
    without = catalog.fit(None, include_uncensored=False)
    assert len(with_unc) > len(without)
    assert not any(c.uncensored for c in without)


def test_fit_modality_filter():
    assert all(c.modality == "code" for c in catalog.fit(None, modality="code"))


def test_by_id_roundtrip():
    assert catalog.by_id("mistral-7b").family == "Mistral"
    assert catalog.by_id("does-not-exist") is None


# --- hardware ----------------------------------------------------------------
def test_detect_returns_sane_shape():
    hw = hardware.detect()
    assert hw.os and hw.arch
    assert hw.cpu_count is None or hw.cpu_count >= 1
    d = hw.to_dict()
    assert {"os", "arch", "cpu_count", "ram_mb", "gpus", "total_vram_mb"} <= d.keys()


def test_usable_vram_never_negative():
    v = hardware.usable_vram_mb()
    assert v is None or v >= 0


# --- manager -----------------------------------------------------------------
def test_tools_reports_both():
    names = {t.name for t in manager.tools()}
    assert names == {"ollama", "huggingface-cli"}


def test_pull_dry_run_builds_right_command():
    ok, msg = manager.pull(catalog.by_id("qwen2.5-7b"), dry_run=True)
    assert ok and "ollama pull qwen2.5:7b" in msg


def test_pull_unknown_scheme():
    bad = catalog.ModelCard("x", "X", 1, "text", 100, "magnet:foo")
    ok, msg = manager.pull(bad)
    assert not ok and "unknown pull scheme" in msg


# --- cluster -----------------------------------------------------------------
def test_readvertise_rewrites_localhost():
    b = Backend(name="ollama", base_url="http://127.0.0.1:11434", models=["m"])
    out = _readvertise(b, "10.0.0.5")
    assert out.base_url == "http://10.0.0.5:11434"


def test_register_into_merges():
    reg = BackendRegistry()
    added = register_into(reg, {"backends": [
        {"name": "node1.ollama", "base_url": "http://10.0.0.5:11434", "models": ["llama3.1:8b"]},
        {"bad": "entry"},  # skipped, not crashed
    ]})
    assert added == ["node1.ollama"]
    assert "llama3.1:8b" in reg.model_catalog()


# --- gateway cluster endpoint (end-to-end) -----------------------------------
@pytest.fixture()
def gateway():
    reg = BackendRegistry()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield reg, "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()


def test_cluster_register_endpoint(gateway):
    reg, url = gateway
    payload = {"node": "edge-1", "address": "10.0.0.9",
               "backends": [{"name": "edge-1.ollama", "base_url": "http://10.0.0.9:11434",
                             "models": ["qwen2.5:7b"]}]}
    req = urllib.request.Request(url + "/cluster/register",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read())
    assert body["ok"] and body["node"] == "edge-1"
    assert "edge-1.ollama" in reg.names()
    # and the coordinator's catalog now lists the node's model
    with urllib.request.urlopen(url + "/cluster/nodes", timeout=5) as resp:
        nodes = json.loads(resp.read())["nodes"]
    assert "edge-1" in nodes
