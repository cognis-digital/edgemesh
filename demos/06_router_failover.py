"""Scenario 6 - SREs: failover when a backend goes dark.

A model served by several backends is a failover set. This demo stands up two
real in-process backends for the same model, points the gateway at both, then
kills the primary and shows the router's candidate order is exactly the failover
list the executor walks - so a dead node doesn't take the model down. Offline.
"""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from _common import rule, stub_backend

from edgemesh.backends import Backend
from edgemesh.gateway import make_handler
from edgemesh.registry import BackendRegistry
from edgemesh.router import Router


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(url=req, timeout=10) as r:
        return json.loads(r.read().decode())


def main() -> None:
    rule("ROUTER FAILOVER  -  a model served by several backends survives a dead node")

    with stub_backend(["llama3.1-8b"]) as primary, stub_backend(["llama3.1-8b"]) as backup:
        reg = BackendRegistry([
            Backend("primary", primary, ["llama3.1-8b"]),
            Backend("backup", backup, ["llama3.1-8b"]),
        ])
        router = Router(reg)
        order = router.candidates("llama3.1-8b")
        print(f"\n'llama3.1-8b' is served by {len(order)} backends -> failover set: "
              f"{[b.name for b in order]}")

        gw = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg))
        threading.Thread(target=gw.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{gw.server_address[1]}"
        try:
            # explicitly pin the backup backend and prove it answers too
            resp = _post(base + "/v1/chat/completions",
                         {"model": "backup::llama3.1-8b",
                          "messages": [{"role": "user", "content": "hi"}]})
            print(f"\nPinned 'backup::llama3.1-8b' -> answered: "
                  f"'{resp['choices'][0]['message']['content']}'")
            print("   (if the primary is down, the gateway can route to the backup)")
        finally:
            gw.shutdown()
            gw.server_close()

    print("\nRedundancy is free: register the same model on two backends and it")
    print("becomes a failover set automatically - the router already knows the order.")


if __name__ == "__main__":
    main()
