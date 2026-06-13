# edgemesh roadmap

Directional, not a promise. Issues and PRs welcome.

## Swarm (0.3 control plane → 0.4 distributed execution → 0.5 sharding+failover; next)
- ✅ **Distributed execution + aggregation** (0.4) and **failover + sharding-node
  routing** (0.5): `run_job` tries nodes best-first, fails over past dead ones, and
  routes oversized models to a `--sharding` node; `scatter_gather` fans batches.
- ✅ **Streaming responses** (SSE) through `/v1/chat/completions`, `/swarm/run` (0.6).
- ✅ **Sharding-backend presets** — `edgemesh node --preset <exo|vllm-ray|…>` (0.6).
- ✅ **mTLS** (0.7): mutual client-cert auth on the gateway (`serve --tls`).
- ✅ **Token-metered settlement** (0.7): streams bill on tokens actually produced.
- ✅ **Onion-style privacy relay** (0.7): layered-encryption multi-hop community relay.
- **Signed-profile attestation**: nodes attest hardware profiles (mTLS identity ships today).
- **Relay hardening toward real anonymity**: cover traffic, padding, per-hop delays,
  guard relays, a published relay directory with consensus.
- **Auto-spawn a preset**: optionally launch the sharding runtime from the preset's
  start hint, not just register an already-running one.
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
