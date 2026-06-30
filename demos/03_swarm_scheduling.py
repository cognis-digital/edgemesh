"""Scenario 3 - distributed-systems teams: the swarm scheduler in motion.

A swarm spans devices of different trust and capability. When a job arrives, the
scheduler runs three gates in order:
  1. PRIVACY  - data sensitivity sets the minimum trust class allowed to touch it.
  2. FIT      - the node must have enough usable VRAM (sharding nodes are exempt).
  3. AUCTION  - among the eligible, reputation/price wins (reliable + cheap).
Then the ledger settles credits consumer -> node and moves reputation. This demo
runs the whole lifecycle against the bundled heterogeneous swarm - in memory.
"""
from _common import fixture_nodes, rule

from edgemesh.protocol import (DATA_CONFIDENTIAL, DATA_PUBLIC, Job)
from edgemesh.scheduler import allowed_classes, eligible, ranked
from edgemesh.swarm import SwarmController


def main() -> None:
    rule("SWARM SCHEDULING  -  privacy gate -> VRAM fit -> reputation auction")

    swarm = SwarmController()
    for n in fixture_nodes():
        swarm.register(n)
    print("\nSwarm membership:")
    for n in swarm.list_nodes():
        vram = n.profile.usable_vram_mb()
        kind = "sharding" if n.sharding else "single-node"
        print(f"   class {n.node_class}  {n.name:<22} {kind:<11} usable_vram="
              f"{vram if vram is not None else '?'} MB")

    # 1) PRIVACY: a confidential job may only land on Class A nodes.
    print("\n[1] PRIVACY GATE")
    conf = Job.new("llama3.3-70b", data_class=DATA_CONFIDENTIAL, min_vram_mb=43000)
    print(f"   confidential job allows classes {sorted(allowed_classes(DATA_CONFIDENTIAL))}; "
          f"eligible nodes: {[n.name for n in eligible(conf, swarm.list_nodes())]}")

    # 2) FIT: a public 70B job needs a big node OR a sharding node.
    print("\n[2] CAPABILITY / VRAM FIT")
    big = Job.new("llama3.3-70b", data_class=DATA_PUBLIC, min_vram_mb=43000)
    elig = eligible(big, swarm.list_nodes())
    print(f"   public 70B (needs 43000 MB) eligible: {[n.name for n in elig]}")
    print("   (the 16 GB laptop is filtered out; the exo sharding node is exempt)")

    # 3) AUCTION + settlement, with the consumer's credits funded first.
    print("\n[3] AUCTION + SETTLEMENT")
    swarm.ledger.grant("acme-co", 100.0)
    small = Job.new("llama3.1-8b", data_class=DATA_PUBLIC, min_vram_mb=6500,
                    submitted_by="acme-co")
    order = ranked(small, swarm.list_nodes(), swarm.ledger, price=2.0)
    print(f"   auction order (best-first): {[n.name for n in order]}")
    assignment = swarm.submit(small, price=2.0)
    print(f"   scheduled job {assignment.job_id} -> {assignment.node_id} @ {assignment.price} credits")

    before = swarm.ledger.rep(assignment.node_id)
    result = swarm.complete(small.job_id, consumer="acme-co", success=True)
    print(f"   settled: paid {result['paid']} credits to {result['node_id']}; "
          f"reputation {before} -> {result['reputation']}")
    print(f"   ledger now: acme-co={swarm.ledger.balance('acme-co')}, "
          f"{assignment.node_id}={swarm.ledger.balance(assignment.node_id)}")

    print("\nPrivacy first, then fit, then price-for-reliability - and the books always balance.")


if __name__ == "__main__":
    main()
