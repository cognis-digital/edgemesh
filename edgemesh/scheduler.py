"""Scheduler — place a job on the best eligible node.

Pipeline (diagram: Privacy Engine -> Scheduler -> Shard Assignment):
  1. **Privacy gate**: a job's data sensitivity sets the minimum node trust class
     allowed to touch it (confidential -> Class A only; private -> A/B; public -> any).
  2. **Capability filter**: the node must have enough usable VRAM for the model.
  3. **Auction**: among eligible nodes, prefer the best score = reputation / price
     (reliable + cheap wins); price defaults to 1 credit when unpriced.
"""

from __future__ import annotations

from edgemesh.ledger import Ledger
from edgemesh.protocol import (CLASS_A, CLASS_B, CLASS_C, DATA_CONFIDENTIAL,
                               DATA_PRIVATE, Assignment, Job, NodeInfo)

# data sensitivity -> set of node classes permitted
_ALLOWED_CLASSES = {
    DATA_CONFIDENTIAL: {CLASS_A},
    DATA_PRIVATE: {CLASS_A, CLASS_B},
    # public -> any (handled as the default below)
}


def allowed_classes(data_class: str) -> set[str]:
    return _ALLOWED_CLASSES.get(data_class, {CLASS_A, CLASS_B, CLASS_C})


def eligible(job: Job, nodes: list[NodeInfo]) -> list[NodeInfo]:
    ok_classes = allowed_classes(job.data_class)
    out = []
    for n in nodes:
        if n.node_class not in ok_classes:
            continue
        # sharding nodes span machines -> exempt from the single-node VRAM filter
        if not n.sharding and job.min_vram_mb:
            vram = n.profile.usable_vram_mb()
            if vram is None or vram < job.min_vram_mb:
                continue
        out.append(n)
    return out


def _score(led: Ledger, n: NodeInfo, price: float) -> float:
    # reliable + cheap wins; a single-fit node is preferred over a sharding node
    # for a model that fits (sharding has coordination overhead).
    base = led.rep(n.node_id) / max(price, 0.01)
    return base * (0.75 if n.sharding else 1.0)


def ranked(job: Job, nodes: list[NodeInfo], ledger: Ledger | None = None,
           price: float = 1.0) -> list[NodeInfo]:
    """Eligible nodes, best-first — used for scheduling and failover."""
    led = ledger or Ledger()
    return sorted(eligible(job, nodes), key=lambda n: _score(led, n, price), reverse=True)


def schedule(job: Job, nodes: list[NodeInfo], ledger: Ledger | None = None,
             price: float = 1.0) -> Assignment | None:
    """Return the winning Assignment, or None if no node is eligible."""
    order = ranked(job, nodes, ledger, price)
    if not order:
        return None
    return Assignment(job_id=job.job_id, node_id=order[0].node_id, price=price)
