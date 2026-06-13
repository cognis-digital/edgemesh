"""Swarm control plane — the orchestration layer over compute nodes.

Holds the **node registry** (compute nodes with their trust class, hardware
profile, and reputation — distinct from `registry.BackendRegistry`, which holds
OpenAI-compatible model backends), and wires it to the **scheduler** and the
**credits/reputation ledger**:

  register/heartbeat  -> a device joins the swarm and stays alive
  submit              -> schedule a job onto the best eligible node (privacy + fit + auction)
  complete            -> settle credits consumer -> node and update reputation

This is the in-memory core; the gateway exposes it over HTTP (`/swarm/*`), and
`node` (CLI) registers a device into it. Pure standard library.
"""

from __future__ import annotations

import time

from edgemesh.ledger import Ledger
from edgemesh.protocol import Assignment, Job, NodeInfo
from edgemesh.scheduler import schedule


class SwarmController:
    def __init__(self, ledger: Ledger | None = None) -> None:
        self.nodes: dict[str, NodeInfo] = {}
        self.ledger = ledger or Ledger()
        self._assignments: dict[str, Assignment] = {}  # job_id -> assignment

    # --- membership ----------------------------------------------------------
    def register(self, node: NodeInfo, *, now: float | None = None) -> NodeInfo:
        node.last_seen = now if now is not None else time.time()
        node.reputation = self.ledger.rep(node.node_id)
        self.nodes[node.node_id] = node
        return node

    def heartbeat(self, node_id: str, *, now: float | None = None) -> bool:
        n = self.nodes.get(node_id)
        if not n:
            return False
        n.last_seen = now if now is not None else time.time()
        return True

    def prune(self, ttl_s: float = 120.0, *, now: float | None = None) -> list[str]:
        now = now if now is not None else time.time()
        dropped = [nid for nid, n in self.nodes.items() if now - n.last_seen > ttl_s]
        for nid in dropped:
            del self.nodes[nid]
        return dropped

    def list_nodes(self, node_class: str | None = None) -> list[NodeInfo]:
        ns = list(self.nodes.values())
        return [n for n in ns if n.node_class == node_class] if node_class else ns

    # --- jobs ----------------------------------------------------------------
    def submit(self, job: Job, *, price: float = 1.0) -> Assignment | None:
        a = schedule(job, list(self.nodes.values()), self.ledger, price=price)
        if a:
            self._assignments[job.job_id] = a
        return a

    def complete(self, job_id: str, consumer: str, success: bool = True) -> dict:
        """Settle a finished job: pay the node and move its reputation."""
        a = self._assignments.pop(job_id, None)
        if not a:
            return {"ok": False, "error": "unknown job"}
        settled = False
        if success:
            settled = self.ledger.settle(consumer, a.node_id, a.price)
        rep = self.ledger.record_outcome(a.node_id, success and settled)
        if a.node_id in self.nodes:
            self.nodes[a.node_id].reputation = rep
        return {"ok": True, "job_id": job_id, "node_id": a.node_id,
                "paid": a.price if settled else 0.0, "reputation": rep}
