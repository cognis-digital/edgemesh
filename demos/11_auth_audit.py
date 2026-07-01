"""Scenario 11 - multi-tenant security: API keys + append-only audit, end to end.

mTLS proves which machine connects; API keys identify which principal is asking,
so you can authorize and audit per tenant. Keys are stored hashed (plaintext shown
once). This demo turns on a keystore, drives the real gateway with and without a
key, and prints the metadata-only audit trail. Offline.
"""
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from _common import rule

from edgemesh.audit import AuditLog
from edgemesh.auth import KeyStore
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry
from edgemesh.swarm import SwarmController


def _try_post(url, body, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    rule("MULTI-TENANT AUTH + AUDIT  -  API keys on top of the gateway")

    ks = KeyStore()
    key = ks.add("alice", scopes=["*"])
    print(f"\nCreated a key for 'alice' (shown ONCE): {key[:12]}...")
    print(f"   stored hashed only; keystore now enforced={ks.enforced}")

    audit_path = os.path.join(tempfile.mkdtemp(prefix="edgemesh_demo_"), "audit.log")
    audit = AuditLog(audit_path)

    gw = ThreadingHTTPServer(("127.0.0.1", 0),
                             make_handler(BackendRegistry(), SwarmController(),
                                          keystore=ks, audit=audit))
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{gw.server_address[1]}"
    try:
        print("\nDriving the protected /swarm/run endpoint:")
        code_noauth = _try_post(base + "/swarm/run", {"model": "m", "messages": []})
        print(f"   no API key       -> HTTP {code_noauth}  (rejected: missing key)")
        code_auth = _try_post(base + "/swarm/run", {"model": "m", "messages": []}, key=key)
        print(f"   valid API key    -> HTTP {code_auth}  (auth passed; 409 = no node, "
              "which is fine here)")
    finally:
        gw.shutdown()
        gw.server_close()

    print("\nAppend-only audit trail (metadata only - never prompt/response content):")
    for ev in audit.tail():
        print(f"   principal={ev['principal']:<10} outcome={ev['outcome']}")

    print("\nOpt-in and dependency-free: no keys = open gateway; add a key and it's enforced.")


if __name__ == "__main__":
    main()
