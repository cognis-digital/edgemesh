# edgemesh roadmap

Directional, not a promise. Issues and PRs welcome.

## Swarm (0.3 control plane + 0.4 distributed execution shipped; next)
- ✅ **Distributed execution + result aggregation** (0.4): `run_job` dispatches a
  scheduled job to the assigned node's backend and settles; `scatter_gather` fans
  batches across nodes. Next: streaming, retries/failover to the next-best node.
- **Tensor-level model sharding**: integrate a sharding backend (exo/Petals/vLLM+Ray)
  as a first-class node type so one oversized model runs across machines.
- **mTLS + signed-profile attestation** between node and control plane (tokens ship today).
- **Resource controls** (CPU/RAM/GPU/power caps) and **sandboxed** job execution on nodes.
- **Pluggable transports**: LAN discovery, mesh, and off-internet adapters behind
  the existing transport seam.
- **Distributed training** pipelines (Class-A nodes) and a **marketplace** UI.

## Near-term (0.3.x)
- **Streaming responses** (`stream: true`) proxied through the gateway (SSE).
- **Health-aware routing**: skip backends failing `/healthz`; round-robin across
  backends that serve the same model.
- **`/v1/embeddings` and `/v1/completions`** passthrough (today: chat + models).
- **Live model pull over HTTP** for backends that support it natively
  (Ollama `POST /api/pull`, LocalAI `POST /models/apply`) — pull to a chosen node
  from the menu without shelling out locally.
- **Node heartbeat / TTL** so a coordinator drops nodes that go away.

## Mid-term
- **Fit-to-cluster placement**: given a model and the cluster's per-node VRAM,
  recommend which node should host it (and warn when nothing fits).
- **Auth**: optional API keys / bearer tokens on the gateway.
- **Adapters** for runtimes that aren't drop-in OpenAI servers (e.g. a Petals
  shim), so they can still join the mesh.
- **Prometheus `/metrics`** and a small status dashboard.

## Exploration
- Tighter, studied interop with cluster orchestrators surfaced in
  [`docs/INTEROP.md`](docs/INTEROP.md) (exo, GPUStack, Ray Serve) where they
  expose stable APIs.
- Optional model-aware load metrics (tokens/s) to inform routing.

See [`CHANGELOG.md`](CHANGELOG.md) for what's already shipped.
