"""Scenario 20 - the whole stack in one story: register -> gate -> fit -> run -> settle.

This is the capstone: a heterogeneous swarm registers, a funded consumer submits a
private job, the privacy gate + VRAM fit + reputation auction pick a node, the
executor forwards the request to a real in-process backend, and the ledger settles
credits and reputation. One narrative through every layer edgemesh provides. Offline.
"""
from _common import rule, stub_backend

from edgemesh.executor import run_job
from edgemesh.protocol import (CLASS_A, CLASS_B, CLASS_C, DATA_PRIVATE,
                               HardwareProfile, Job, NodeInfo)
from edgemesh.scheduler import ranked
from edgemesh.swarm import SwarmController


def _node(nid, cls, vram, endpoint, accel="cuda"):
    return NodeInfo(nid, nid, cls, endpoint,
                    HardwareProfile(os="L", arch="x", accelerator=accel,
                                    ram_mb=64000, vram_mb=vram, gpu_name="G"))


def main() -> None:
    rule("END TO END  -  every layer, one job, start to finish")

    with stub_backend(["llama3.1-8b"]) as trusted_url, stub_backend(["llama3.1-8b"]) as private_url:
        sc = SwarmController()
        sc.ledger.grant("acme-co", 100.0)

        # A three-node swarm: trusted A, private B, public C.
        sc.register(_node("dc-a100", CLASS_A, 80000, trusted_url))
        sc.register(_node("team-box", CLASS_B, 24000, private_url))
        sc.register(_node("community", CLASS_C, 12000, "http://community:8000"))
        # give the private box a slight reputation edge so the auction is interesting
        sc.ledger.reputation["team-box"] = 2.0
        sc.nodes["team-box"].reputation = 2.0
        print(f"\n[1] REGISTERED  swarm size = {len(sc.nodes)}  "
              f"(classes {sorted(n.node_class for n in sc.list_nodes())})")

        # A PRIVATE job: the public community node is gated out entirely.
        job = Job.new("llama3.1-8b", data_class=DATA_PRIVATE, min_vram_mb=6500,
                      submitted_by="acme-co")
        order = ranked(job, sc.list_nodes(), sc.ledger, price=2.0)
        print(f"[2] PRIVACY GATE + FIT + AUCTION  eligible best-first: "
              f"{[n.node_id for n in order]}")
        print("    (community C is excluded by the privacy gate; A and B remain)")

        # [3] EXECUTE against the winning node's real backend.
        res = run_job(sc, job, {"messages": [{"role": "user", "content": "quarterly summary"}]},
                      "acme-co", price=2.0)
        answer = res["result"]["choices"][0]["message"]["content"]
        print(f"[3] EXECUTED   answered_by={res['node_id']}  reply='{answer}'")

        # [4] SETTLE.
        print(f"[4] SETTLED    paid {res['paid']} credits; acme-co="
              f"{sc.ledger.balance('acme-co')}, {res['node_id']}="
              f"{sc.ledger.balance(res['node_id'])}, reputation={res['reputation']}")

    print("\nOne funded request went in; the mesh gated it for privacy, fit it to")
    print("hardware, auctioned it to a reliable node, ran it, and balanced the books.")


if __name__ == "__main__":
    main()
