"""Onion-style relay: a request traverses a 3-relay circuit and reaches the
compute backend, with each relay peeling exactly one layer. Skipped if the
optional `cryptography` dep is absent (the relay fails closed, never fakes it)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from edgemesh import relay
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry

pytestmark = pytest.mark.skipif(not relay.HAVE_CRYPTO, reason="cryptography not installed")


class _Echo(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        prompt = body.get("messages", [{}])[-1].get("content", "")
        out = json.dumps({"choices": [{"message": {"content": f"echo:{prompt}"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def _spawn(handler_cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


@pytest.fixture()
def topology():
    servers = []
    # compute backend (the exit relay delivers here)
    be_srv, backend = _spawn(_Echo)
    servers.append(be_srv)
    # three relays, each with its own identity
    relays = []
    for _ in range(3):
        priv, pub = relay.gen_keypair()
        srv, url = _spawn(make_handler(BackendRegistry(), relay_priv=priv))
        servers.append(srv)
        relays.append((url, pub))
    yield backend, relays
    for s in servers:
        s.shutdown()


def test_three_hop_circuit_delivers(topology):
    backend, relays = topology
    payload = {"messages": [{"role": "user", "content": "secret"}]}
    blob = relay.build_onion(relays, backend, payload)
    resp = relay._post_forward(relays[0][0], blob)
    assert resp["choices"][0]["message"]["content"] == "echo:secret"


def test_send_via_circuit_fetches_keys(topology):
    backend, relays = topology
    endpoints = [u for u, _ in relays]
    resp = relay.send_via_circuit(endpoints, backend,
                                  {"messages": [{"role": "user", "content": "hi"}]})
    assert resp["choices"][0]["message"]["content"] == "echo:hi"


def test_relay_info_exposes_pubkey(topology):
    import urllib.request
    _, relays = topology
    url, pub = relays[0]
    with urllib.request.urlopen(url + "/relay/info", timeout=5) as r:
        info = json.loads(r.read())
    assert info["public_key"] == pub and info["relay_id"] == pub[:12]


def test_wrong_relay_cannot_peel_layer(topology):
    # a relay can only decrypt layers sealed to its own key
    _, relays = topology
    other_priv, _ = relay.gen_keypair()
    blob = relay.seal(relays[0][1], b"for-relay-0")
    with pytest.raises(Exception):
        relay.unseal(other_priv, blob)
