"""Scenario 7 - distributed inference: schedule -> execute -> settle, with failover.

The executor is the real end-to-end path: it schedules a job onto the best node,
forwards the OpenAI request to that node's backend, returns the answer, and
settles credits + reputation. When the best node fails, it fails over to the next.
This demo wires two in-process backends into a swarm - one healthy, one broken -
and shows run_job pay the node that actually answered. Offline.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from _common import rule, stub_backend

from edgemesh.executor import run_job
from edgemesh.protocol import CLASS_C, HardwareProfile, Job, NodeInfo
from edgemesh.swarm import SwarmController


class _Broken(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.send_response(500)
        self.end_headers()


def _node(nid, endpoint):
    return NodeInfo(nid, nid, CLASS_C, endpoint,
                    HardwareProfile(os="L", arch="x", accelerator="cuda",
                                    ram_mb=32000, vram_mb=12000, gpu_name="G"))


def main() -> None:
    rule("DISTRIBUTED EXECUTION  -  run_job schedules, runs, fails over, and settles")

    broken = ThreadingHTTPServer(("127.0.0.1", 0), _Broken)
    threading.Thread(target=broken.serve_forever, daemon=True).start()
    broken_url = f"http://127.0.0.1:{broken.server_address[1]}"

    with stub_backend(["llama3.1-8b"]) as good_url:
        sc = SwarmController()
        sc.ledger.grant("acme-co", 100.0)
        # bias the auction so the BROKEN node is tried first -> forces a failover
        sc.ledger.reputation["broken"] = 4.0
        sc.ledger.reputation["healthy"] = 1.0
        sc.register(_node("broken", broken_url))
        sc.register(_node("healthy", good_url))
        print("\nSwarm: 'broken' (rep 4.0, tried first) and 'healthy' (rep 1.0).")

        job = Job.new("llama3.1-8b", min_vram_mb=6500, submitted_by="acme-co")
        res = run_job(sc, job, {"messages": [{"role": "user", "content": "ping"}]},
                      "acme-co", price=2.0)
        print(f"\nrun_job -> ok={res['ok']} answered_by={res['node_id']} paid={res['paid']}")
        print(f"   failover attempts before success: "
              f"{[a['node_id'] for a in res['attempts']]}")
        print(f"   ledger: acme-co={sc.ledger.balance('acme-co')}, "
              f"healthy={sc.ledger.balance('healthy')}")
        print(f"   reputation moved: broken={sc.ledger.rep('broken')} (penalized), "
              f"healthy={sc.ledger.rep('healthy')} (rewarded)")
    broken.shutdown()
    broken.server_close()

    print("\nThe consumer pays only the node that actually delivered; a flaky node")
    print("is penalized and drops down the auction for next time.")


if __name__ == "__main__":
    main()
