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
from edgemesh.scheduler import eligible, ranked
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


def open_stream(endpoint: str, payload: dict, timeout: float = 300.0):
    """Open a streaming chat request; returns the live response to relay + close."""
    url = endpoint.rstrip("/") + "/v1/chat/completions"
    req = urllib.request.Request(url, data=json.dumps({**payload, "stream": True}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=timeout)


def iter_chunks(resp, size: int = 1024):
    """Yield raw bytes from a streaming response until EOF, then close it."""
    try:
        for chunk in iter(lambda: resp.read(size), b""):
            yield chunk
    finally:
        resp.close()


def content_of(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""


def needs_sharding(job: Job, nodes) -> bool:
    """True if no single eligible node can hold the model (-> needs a sharding backend)."""
    return job.min_vram_mb > 0 and not eligible(job, nodes)


def run_job(swarm: SwarmController, job: Job, payload: dict, consumer: str,
            *, price: float = 1.0, timeout: float = 300.0, max_attempts: int = 3) -> dict:
    """Schedule -> execute -> settle, with failover to the next-best node.

    Oversized models (no single node fits) route to a sharding-capable node if one
    is registered; otherwise a clear error explains how to add one.
    """
    runnable = _runnable(list(swarm.nodes.values()))
    order = ranked(job, runnable, swarm.ledger, price)
    if not order:
        if needs_sharding(job, runnable):
            return {"ok": False, "error": "model does not fit any single node and no "
                    "sharding-capable node is registered — add one with "
                    "`edgemesh node <coordinator> --sharding --serve-url <exo/vLLM /v1>`"}
        return {"ok": False, "error": "no eligible runnable node for this job"}

    payload = {**payload, "model": job.model}
    attempts: list[dict] = []
    for node in order[:max_attempts]:
        try:
            resp = call_backend(node.endpoint, payload, timeout=timeout)
        except Exception as exc:  # node failed -> penalize + fail over
            rep = swarm.ledger.record_outcome(node.node_id, False)
            if node.node_id in swarm.nodes:
                swarm.nodes[node.node_id].reputation = rep
            attempts.append({"node_id": node.node_id, "error": str(exc)})
            continue
        paid = price if swarm.ledger.settle(consumer, node.node_id, price) else 0.0
        rep = swarm.ledger.record_outcome(node.node_id, True)
        if node.node_id in swarm.nodes:
            swarm.nodes[node.node_id].reputation = rep
        return {"ok": True, "node_id": node.node_id, "sharded": node.sharding,
                "result": resp, "paid": paid, "reputation": rep, "attempts": attempts}
    return {"ok": False, "error": f"all {len(attempts)} candidate node(s) failed",
            "attempts": attempts}


class StreamMeter:
    """Counts completion tokens as an OpenAI SSE stream flows past.

    Prefers an explicit `usage.completion_tokens` (emitted by backends when
    `stream_options.include_usage` is set); otherwise approximates by counting
    content-bearing delta chunks (one delta ~= one token, the common case).
    """

    def __init__(self) -> None:
        self._buf = b""
        self._deltas = 0
        self._explicit: int | None = None

    def feed(self, chunk: bytes) -> None:
        self._buf += chunk
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]" or not data:
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            usage = obj.get("usage") or {}
            if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                self._explicit = int(usage["completion_tokens"])
            try:
                if obj["choices"][0].get("delta", {}).get("content"):
                    self._deltas += 1
            except (KeyError, IndexError, TypeError):
                pass

    @property
    def tokens(self) -> int:
        return self._explicit if self._explicit is not None else self._deltas


def stream_job(swarm: SwarmController, job: Job, payload: dict, consumer: str,
               *, price: float = 1.0, timeout: float = 300.0, max_attempts: int = 3):
    """Open a streaming job with failover. Returns (node_id, live_response, attempts).

    No settlement here — settlement is metered on the tokens actually streamed; the
    caller wraps the response with `metered_stream` to charge + reward on completion.
    """
    runnable = _runnable(list(swarm.nodes.values()))
    order = ranked(job, runnable, swarm.ledger, price)
    payload = {**payload, "model": job.model}
    attempts: list[dict] = []
    for node in order[:max_attempts]:
        try:
            resp = open_stream(node.endpoint, payload, timeout=timeout)
        except Exception as exc:
            rep = swarm.ledger.record_outcome(node.node_id, False)
            if node.node_id in swarm.nodes:
                swarm.nodes[node.node_id].reputation = rep
            attempts.append({"node_id": node.node_id, "error": str(exc)})
            continue
        return node.node_id, resp, attempts
    return None, None, attempts


def metered_stream(resp, swarm: SwarmController, node_id: str, consumer: str,
                   price_per_token: float, *, min_charge: float = 0.0):
    """Relay generator: yield chunks, meter tokens, and settle on completion.

    Charge = max(min_charge, tokens * price_per_token), moved consumer -> node;
    reputation rises on a clean finish. Settlement runs in `finally`, so a client
    disconnect still bills for what was produced.
    """
    meter = StreamMeter()
    ok = False
    try:
        for chunk in iter_chunks(resp):
            meter.feed(chunk)
            yield chunk
        ok = True
    finally:
        charge = max(min_charge, meter.tokens * price_per_token)
        swarm.ledger.settle(consumer, node_id, charge)
        rep = swarm.ledger.record_outcome(node_id, ok)
        if node_id in swarm.nodes:
            swarm.nodes[node_id].reputation = rep


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
