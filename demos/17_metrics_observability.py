"""Scenario 17 - observability: Prometheus metrics ops teams expect.

edgemesh exposes GET /metrics in the Prometheus text exposition format - request
counters (labeled by route) plus live gauges rendered on demand from the registry,
swarm, and ledger. This demo drives a few requests through the real gateway and
prints the scrape. Pure standard library, no client dependency. Offline.
"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from _common import rule, stub_backend

from edgemesh.backends import Backend
from edgemesh.gateway import make_handler
from edgemesh.metrics import Metrics
from edgemesh.registry import BackendRegistry
from edgemesh.swarm import SwarmController


def _quiet_post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError:
        pass  # a 409/404 still increments the request counter, which is the point


def main() -> None:
    rule("METRICS / OBSERVABILITY  -  Prometheus scrape from the real gateway")

    metrics = Metrics()
    with stub_backend(["llama3.1-8b"]) as url:
        reg = BackendRegistry([Backend("stub", url, ["llama3.1-8b"])])
        sc = SwarmController()
        sc.ledger.grant("acme-co", 50.0)
        gw = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg, sc, metrics=metrics))
        threading.Thread(target=gw.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{gw.server_address[1]}"
        try:
            print("\nDriving a few requests (some will 409 - that's fine, they still count):")
            _quiet_post(base, "/swarm/submit", {"model": "llama3.1-8b"})
            _quiet_post(base, "/swarm/map", {"model": "llama3.1-8b", "prompts": ["x"]})
            _quiet_post(base, "/v1/chat/completions",
                        {"model": "llama3.1-8b", "messages": [{"role": "user", "content": "hi"}]})

            with urllib.request.urlopen(base + "/metrics", timeout=10) as r:
                content_type = r.headers.get("Content-Type", "")
                body = r.read().decode()
            print(f"\nGET /metrics -> Content-Type: {content_type}")
            print("Exposition (edgemesh_ series only):")
            for line in body.splitlines():
                if line.startswith("edgemesh_"):
                    print(f"   {line}")
        finally:
            gw.shutdown()
            gw.server_close()

    print("\nCounters for traffic, live gauges for backends/nodes/credits - scrape it")
    print("with any Prometheus and you have dashboards before you adopt.")


if __name__ == "__main__":
    main()
