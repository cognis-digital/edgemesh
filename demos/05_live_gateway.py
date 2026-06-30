"""Scenario 5 - ops & compliance: a real gateway round-trip, observed.

This stands up the actual edgemesh gateway (stdlib http.server) in front of a
bundled in-process OpenAI-compatible backend - no external server, no network -
and drives real HTTP through it: GET /v1/models, POST /v1/chat/completions, GET
/metrics. It also attaches the append-only audit log so you see the metadata-only
compliance trail (prompt/response content is never logged).
"""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from _common import rule, stub_backend

from edgemesh.audit import AuditLog
from edgemesh.backends import Backend
from edgemesh.gateway import make_handler
from edgemesh.metrics import Metrics
from edgemesh.registry import BackendRegistry


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read().decode()


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main() -> None:
    rule("LIVE GATEWAY  -  real /v1 round-trip, with metrics + audit")

    import tempfile, os
    audit_path = os.path.join(tempfile.mkdtemp(prefix="edgemesh_demo_"), "audit.log")
    audit = AuditLog(audit_path)
    metrics = Metrics()

    # A real backend (in-process stub) + the real gateway in front of it.
    with stub_backend(["llama3.1-8b", "mistral-7b"]) as backend_url:
        reg = BackendRegistry([Backend("local-stub", backend_url,
                                       ["llama3.1-8b", "mistral-7b"])])
        handler = make_handler(reg, audit=audit, metrics=metrics)
        gw = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=gw.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{gw.server_address[1]}"
        try:
            code, body = _get(base + "/v1/models")
            models = [m["id"] for m in json.loads(body)["data"]]
            print(f"\nGET /v1/models -> {code}; aggregated catalog: {models}")

            chat = _post(base + "/v1/chat/completions",
                         {"model": "llama3.1-8b",
                          "messages": [{"role": "user", "content": "ping"}]})
            answer = chat["choices"][0]["message"]["content"]
            print(f"POST /v1/chat/completions (model=llama3.1-8b) -> '{answer}'")
            print("   (the gateway routed this to 'local-stub' and relayed its reply verbatim)")

            code, mbody = _get(base + "/metrics")
            print(f"\nGET /metrics -> {code}; Prometheus exposition (excerpt):")
            for line in mbody.splitlines():
                if line.startswith("edgemesh_") and not line.startswith("#"):
                    print(f"   {line}")
        finally:
            gw.shutdown()
            gw.server_close()

    print("\nAppend-only audit trail (metadata only - never prompt/response content):")
    for ev in audit.tail(10):
        print(f"   {ev['action']:<24} principal={ev['principal']:<10} outcome={ev['outcome']}")

    print("\nA gateway you can put in front of anything, observe with Prometheus, and")
    print("hand a regulator an audit trail for - all on the standard library.")


if __name__ == "__main__":
    main()
