"""API-key access control + append-only audit logging, incl. the gateway gate."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from edgemesh.audit import AuditLog
from edgemesh.auth import KeyStore
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry
from edgemesh.swarm import SwarmController


# --- KeyStore ----------------------------------------------------------------
def test_keystore_add_verify_and_hashing():
    ks = KeyStore()
    assert not ks.enforced
    key = ks.add("alice")
    assert key.startswith("em_") and ks.enforced
    assert ks.verify(key)["name"] == "alice"
    assert ks.verify("em_wrong") is None
    # plaintext is never stored — only its hash is a dict key
    assert key not in ks.keys and all(len(h) == 64 for h in ks.keys)


def test_principal_from_header_bearer_and_raw():
    ks = KeyStore()
    key = ks.add("svc")
    assert ks.principal_from_header(f"Bearer {key}")["name"] == "svc"
    assert ks.principal_from_header(key)["name"] == "svc"
    assert ks.principal_from_header(None) is None


def test_keystore_roundtrip(tmp_path):
    ks = KeyStore(); key = ks.add("t")
    p = str(tmp_path / "keys.json"); ks.save(p)
    assert KeyStore.load(p).verify(key)["name"] == "t"


# --- AuditLog ----------------------------------------------------------------
def test_audit_appends_metadata_only(tmp_path):
    log = AuditLog(str(tmp_path / "audit.log"))
    log.record("/swarm/run", principal="alice", client="10.0.0.1", model="llama", outcome="accepted")
    log.record("/swarm/run", principal="bob", client="10.0.0.2", outcome="denied:auth")
    events = log.tail()
    assert len(events) == 2 and events[0]["principal"] == "alice"
    # no prompt/response content captured
    assert all("messages" not in e and "content" not in e for e in events)


# --- gateway gate (e2e) ------------------------------------------------------
@pytest.fixture()
def gated(tmp_path):
    ks = KeyStore(); key = ks.add("tester")
    audit = AuditLog(str(tmp_path / "a.log"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(BackendRegistry(), SwarmController(),
                                                             keystore=ks, audit=audit))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield key, audit, "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _post(url, payload, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    return urllib.request.urlopen(req, timeout=5)


def test_gateway_requires_key_when_enforced(gated):
    key, audit, base = gated
    # no key -> 401
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/swarm/run", {"model": "m", "messages": []})
    assert e.value.code == 401
    # valid key -> passes auth (409 = no eligible node, NOT 401)
    with pytest.raises(urllib.error.HTTPError) as e2:
        _post(base + "/swarm/run", {"model": "m", "messages": []}, key=key)
    assert e2.value.code == 409
    # audit captured both a denial and an acceptance
    outcomes = [e["outcome"] for e in audit.tail()]
    assert "denied:auth" in outcomes and "accepted" in outcomes
