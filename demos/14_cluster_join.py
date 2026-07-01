"""Scenario 14 - build a cluster: a node joins a coordinator over real HTTP.

One node runs the coordinator (the gateway). Every other device runs
`edgemesh join <coordinator>`: it discovers its local OpenAI-compatible backends,
rewrites localhost URLs to a reachable address, namespaces them by node, and
registers them - so the coordinator's single /v1 catalog spans the whole cluster.
This demo does a real join against an in-process coordinator. Offline.
"""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from _common import rule

from edgemesh.cluster import register_into
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry


def _register(base, payload):
    req = urllib.request.Request(base + "/cluster/register",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main() -> None:
    rule("CLUSTER JOIN  -  a device registers its backends with the coordinator")

    reg = BackendRegistry()
    gw = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg))
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{gw.server_address[1]}"
    print(f"\nCoordinator up at {base} with an empty catalog.")

    try:
        # Simulate two devices joining. Each advertises its own localhost backends,
        # rewritten to a reachable host and namespaced by node name.
        for node, host, models in [
            ("gpu-box", "10.0.0.7", ["llama3.1-8b", "qwen2.5-coder-7b"]),
            ("mac-studio", "10.0.0.9", ["mistral-7b"]),
        ]:
            payload = {"node": node, "address": host, "backends": [
                {"name": f"{node}.ollama", "base_url": f"http://{host}:11434", "models": models}]}
            resp = _register(base, payload)
            print(f"\n{node} joined -> added {resp['added']}; "
                  f"coordinator catalog is now {resp['catalog_size']} model(s)")

        with urllib.request.urlopen(base + "/v1/models", timeout=10) as r:
            catalog = [m["id"] for m in json.loads(r.read())["data"]]
        print(f"\nUnified /v1 catalog across the cluster: {sorted(catalog)}")
    finally:
        gw.shutdown()
        gw.server_close()

    # register_into is the coordinator-side merge; it tolerates malformed entries
    local = BackendRegistry()
    added = register_into(local, {"backends": [{"garbage": 1},
                                  {"name": "ok", "base_url": "http://h:1", "models": []}]})
    print(f"\nCoordinator merge is fault-tolerant: malformed entry skipped, added={added}")

    print("\nAny OS, any device - one endpoint that spans them all.")


if __name__ == "__main__":
    main()
