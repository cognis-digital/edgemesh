"""Backend parsing, discovery, and registry edge cases."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from edgemesh.backends import (KNOWN_PORTS, Backend, discover, parse_models,
                               probe)
from edgemesh.registry import BackendRegistry


# --- parse_models ------------------------------------------------------------
def test_parse_openai_shape_sorted():
    assert parse_models({"data": [{"id": "b"}, {"id": "a"}]}) == ["a", "b"]


def test_parse_bare_list_dedup():
    assert parse_models(["x", "x", "y"]) == ["x", "y"]


def test_parse_mixed_str_and_dict():
    assert parse_models({"data": ["a", {"id": "b"}]}) == ["a", "b"]


def test_parse_garbage_returns_empty():
    assert parse_models(None) == []
    assert parse_models(42) == []
    assert parse_models("string") == []


def test_parse_skips_items_without_id():
    assert parse_models({"data": [{"no_id": 1}, {"id": "keep"}]}) == ["keep"]


def test_parse_empty_data():
    assert parse_models({"data": []}) == []


# --- Backend dataclass -------------------------------------------------------
def test_backend_to_dict_strips_trailing_slash():
    b = Backend("n", "http://h:1/", ["m"])
    assert b.to_dict()["base_url"] == "http://h:1"


def test_backend_from_dict():
    b = Backend.from_dict({"name": "n", "base_url": "http://h:1/", "models": ["m"]})
    assert b.name == "n" and b.base_url == "http://h:1"


def test_backend_from_dict_missing_models():
    b = Backend.from_dict({"name": "n", "base_url": "http://h:1"})
    assert b.models == []


def test_backend_urls():
    b = Backend("n", "http://h:1/")
    assert b.models_url() == "http://h:1/v1/models"
    assert b.chat_url() == "http://h:1/v1/chat/completions"


# --- probe / discover --------------------------------------------------------
def test_probe_unreachable_returns_none():
    assert probe("http://127.0.0.1:1", timeout=0.5) is None


class _Models(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        out = json.dumps({"data": [{"id": "m1"}, {"id": "m2"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def test_probe_reachable_returns_models():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Models)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        assert probe(base, timeout=5) == ["m1", "m2"]
    finally:
        srv.shutdown()


def test_discover_with_reachable_port():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Models)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]
        found = discover(host="127.0.0.1", ports={port: "test-backend"}, timeout=5)
        assert len(found) == 1 and found[0].name == "test-backend"
        assert found[0].models == ["m1", "m2"]
    finally:
        srv.shutdown()


def test_discover_no_backends_when_ports_dead():
    assert discover(host="127.0.0.1", ports={1: "dead"}, timeout=0.5) == []


def test_known_ports_covers_fleet_and_common_runtimes():
    names = set(KNOWN_PORTS.values())
    assert {"uncensored-fleet", "coding-fleet", "vision-fleet", "ollama"} <= names
    assert 11434 in KNOWN_PORTS  # ollama default


# --- registry ----------------------------------------------------------------
def test_registry_add_replace_by_name():
    reg = BackendRegistry()
    reg.add(Backend("a", "http://h:1", ["old"]))
    reg.add(Backend("a", "http://h:2", ["new"]))
    assert reg.get("a").models == ["new"]  # replaced, not duplicated
    assert reg.names() == ["a"]


def test_registry_remove():
    reg = BackendRegistry([Backend("a", "http://h:1", ["m"])])
    reg.remove("a")
    assert reg.names() == []


def test_registry_remove_missing_is_noop():
    reg = BackendRegistry()
    reg.remove("ghost")  # must not raise
    assert reg.names() == []


def test_registry_names_sorted():
    reg = BackendRegistry([Backend("z", "http://h:1", []), Backend("a", "http://h:2", [])])
    assert reg.names() == ["a", "z"]


def test_registry_catalog_dedups_owners():
    reg = BackendRegistry([Backend("a", "http://h:1", ["m", "m"])])
    assert reg.model_catalog()["m"] == ["a"]


def test_registry_config_roundtrip(tmp_path):
    path = str(tmp_path / "c.json")
    BackendRegistry([Backend("a", "http://h:1", ["m"])]).save(path)
    assert BackendRegistry.load(path).get("a").models == ["m"]


def test_registry_load_missing_empty(tmp_path):
    assert BackendRegistry.load(str(tmp_path / "no.json")).names() == []
