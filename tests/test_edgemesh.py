"""Tests for edgemesh: parsing, registry/catalog, routing, and a live gateway round-trip."""

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from edgemesh.backends import Backend, parse_models
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry
from edgemesh.router import NoBackendError, Router


def test_parse_models_openai_shape():
    assert parse_models({"data": [{"id": "b"}, {"id": "a"}]}) == ["a", "b"]


def test_parse_models_bare_list_and_dedup():
    assert parse_models(["x", "x", "y"]) == ["x", "y"]


def test_parse_models_garbage_is_empty():
    assert parse_models(None) == [] and parse_models(42) == []


def test_catalog_aggregates_across_backends():
    reg = BackendRegistry([
        Backend("fleet", "http://h:1", ["shared", "only-fleet"]),
        Backend("ollama", "http://h:2", ["shared", "only-ollama"]),
    ])
    catalog = reg.model_catalog()
    assert catalog["shared"] == ["fleet", "ollama"]
    assert catalog["only-fleet"] == ["fleet"]


def test_router_resolves_by_model():
    reg = BackendRegistry([Backend("fleet", "http://h:1", ["m1"])])
    backend, upstream = Router(reg).resolve("m1")
    assert backend.name == "fleet" and upstream == "m1"


def test_router_explicit_backend_syntax():
    reg = BackendRegistry([
        Backend("a", "http://h:1", ["m"]),
        Backend("b", "http://h:2", ["m"]),
    ])
    backend, upstream = Router(reg).resolve("b::m")
    assert backend.name == "b" and upstream == "m"


def test_router_unknown_model_raises():
    reg = BackendRegistry([Backend("a", "http://h:1", ["m"])])
    with pytest.raises(NoBackendError):
        Router(reg).resolve("nope")


def test_router_unknown_explicit_backend_raises():
    reg = BackendRegistry([Backend("a", "http://h:1", ["m"])])
    with pytest.raises(NoBackendError):
        Router(reg).resolve("ghost::m")


def test_registry_roundtrips_through_config(tmp_path):
    path = str(tmp_path / "config.json")
    BackendRegistry([Backend("a", "http://h:1", ["m"])]).save(path)
    reloaded = BackendRegistry.load(path)
    assert reloaded.names() == ["a"]
    assert reloaded.get("a").models == ["m"]


def test_load_missing_config_is_empty(tmp_path):
    assert BackendRegistry.load(str(tmp_path / "absent.json")).names() == []


# --- live gateway round-trip against a stub upstream ---------------------

def _run_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_gateway_routes_chat_to_correct_backend():
    # Stub upstream that echoes the model it received.
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            received = json.loads(self.rfile.read(n))
            out = json.dumps({"echo_model": received["model"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    upstream = _run_server(Upstream)
    try:
        port = upstream.server_address[1]
        reg = BackendRegistry([Backend("stub", f"http://127.0.0.1:{port}", ["demo-model"])])
        gateway = _run_server(make_handler(reg))
        try:
            gport = gateway.server_address[1]
            # catalog endpoint
            with urllib.request.urlopen(f"http://127.0.0.1:{gport}/v1/models", timeout=5) as r:
                catalog = json.loads(r.read())
            assert catalog["data"][0]["id"] == "demo-model"
            # chat is routed and forwarded; upstream echoes the (unprefixed) model
            req = urllib.request.Request(
                f"http://127.0.0.1:{gport}/v1/chat/completions",
                data=json.dumps({"model": "stub::demo-model", "messages": []}).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                result = json.loads(r.read())
            assert result == {"echo_model": "demo-model"}
        finally:
            gateway.shutdown()
    finally:
        upstream.shutdown()


def test_gateway_unknown_model_returns_404():
    reg = BackendRegistry([Backend("stub", "http://127.0.0.1:1", ["known"])])
    gateway = _run_server(make_handler(reg))
    try:
        gport = gateway.server_address[1]
        req = urllib.request.Request(
            f"http://127.0.0.1:{gport}/v1/chat/completions",
            data=json.dumps({"model": "unknown", "messages": []}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        assert exc.value.code == 404
    finally:
        gateway.shutdown()
