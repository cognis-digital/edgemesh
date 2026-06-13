"""Distributed execution + result aggregation over the swarm.

What this *does* (real, works today):
  - **run_job**: schedule a chat job onto the best eligible node, forward the
    OpenAI request to that node's backend, return the result, and settle credits +
    reputation on the ledger. End-to-end distributed execution over the mesh.
  - **scatter_gather**: fan a batch of prompts (or N replicas of one prompt) across
    eligible nodes concurrently and aggregate (first | concat | vote | all). This
    is genuine data-parallel distributed inference.

What this does *not* do (and doesn't pretend to):
  - tensor-level **model sharding** / pipeline parallelism (one model split across
    machines layer-by-layer). That is delegated to a sharding-capable backend
    (exo, Petals, vLLM+Ray, llama.cpp RPC) registered as a node — see
    `needs_sharding()` / ROADMAP. edgemesh routes to such a backend; it does not
    reimplement it.

Pure standard library (urllib + threads).
"""

from __future__ import annotations

import json
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from edgemesh.protocol import Job
from edgemesh.scheduler import eligible
from edgemesh.swarm import SwarmController


def _runnable(nodes):
    return [n for n in nodes if n.endpoint]


def call_backend(endpoint: str, payload: dict, timeout: float = 300.0) -> dict:
    """POST an OpenAI chat request to a node's backend and return the JSON."""
    url = endpoint.rstrip("/") + "/v1/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def content_of(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""


def needs_sharding(job: Job, nodes) -> bool:
    """True if no single eligible node can hold the model (-> needs a sharding backend)."""
    return job.min_vram_mb > 0 and not eligible(job, nodes)


def run_job(swarm: SwarmController, job: Job, payload: dict, consumer: str,
            *, price: float = 1.0, timeout: float = 300.0) -> dict:
    """Schedule -> execute on the assigned node -> settle. Returns a result dict."""
    runnable = _runnable(list(swarm.nodes.values()))
    if needs_sharding(job, runnable):
        return {"ok": False, "error": "model does not fit any single node; register a "
                "sharding-capable backend (exo/Petals/vLLM+Ray/llama.cpp-RPC) as a node"}
    a = swarm.submit(job, price=price)
    if not a:
        return {"ok": False, "error": "no eligible node for this job"}
    node = swarm.nodes.get(a.node_id)
    if not node or not node.endpoint:
        swarm.complete(job.job_id, consumer, success=False)
        return {"ok": False, "error": f"assigned node {a.node_id} has no servable endpoint"}
    payload = {**payload, "model": job.model}
    try:
        resp = call_backend(node.endpoint, payload, timeout=timeout)
    except Exception as exc:
        settle = swarm.complete(job.job_id, consumer, success=False)
        return {"ok": False, "error": f"node {a.node_id} failed: {exc}", **settle}
    settle = swarm.complete(job.job_id, consumer, success=True)
    return {"ok": True, "node_id": a.node_id, "result": resp,
            "paid": settle.get("paid"), "reputation": settle.get("reputation")}


def scatter_gather(swarm: SwarmController, model: str, prompts: list[str],
                   *, aggregate: str = "all", data_class: str = "public",
                   min_vram_mb: int = 0, timeout: float = 300.0) -> dict:
    """Distribute prompts across eligible nodes concurrently and aggregate.

    aggregate: 'all' (list), 'first' (first ok), 'concat' (join contents),
               'vote' (most-common content).
    """
    probe = Job.new(model, data_class=data_class, min_vram_mb=min_vram_mb)
    nodes = _runnable(eligible(probe, list(swarm.nodes.values())))
    if not nodes:
        return {"ok": False, "error": "no eligible runnable nodes"}

    def work(i_prompt):
        i, prompt = i_prompt
        node = nodes[i % len(nodes)]          # round-robin placement
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        try:
            return {"prompt": prompt, "node_id": node.node_id,
                    "content": content_of(call_backend(node.endpoint, payload, timeout=timeout))}
        except Exception as exc:
            return {"prompt": prompt, "node_id": node.node_id, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=min(8, len(nodes) * 2)) as pool:
        results = list(pool.map(work, enumerate(prompts)))

    oks = [r["content"] for r in results if "content" in r]
    if aggregate == "first":
        agg = oks[0] if oks else None
    elif aggregate == "concat":
        agg = "\n".join(oks)
    elif aggregate == "vote":
        agg = Counter(oks).most_common(1)[0][0] if oks else None
    else:
        agg = results
    return {"ok": True, "nodes_used": sorted({r["node_id"] for r in results}),
            "count": len(results), "aggregate": aggregate, "result": agg, "results": results}
