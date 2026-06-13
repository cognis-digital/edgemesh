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
        vram = n.profile.usable_vram_mb()
        if job.min_vram_mb and (vram is None or vram < job.min_vram_mb):
            continue
        out.append(n)
    return out


def schedule(job: Job, nodes: list[NodeInfo], ledger: Ledger | None = None,
             price: float = 1.0) -> Assignment | None:
    """Return the winning Assignment, or None if no node is eligible."""
    cands = eligible(job, nodes)
    if not cands:
        return None
    led = ledger or Ledger()

    def score(n: NodeInfo) -> float:
        return led.rep(n.node_id) / max(price, 0.01)

    winner = max(cands, key=score)
    return Assignment(job_id=job.job_id, node_id=winner.node_id, price=price)
