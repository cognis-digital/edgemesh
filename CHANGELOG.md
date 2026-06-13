# Changelog

All notable changes to edgemesh are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions use SemVer.

## [0.6.0] — 2026-06-13

The "streaming + presets" release.

### Added
- **Streaming (SSE)**: `stream: true` now streams token-by-token through the
  gateway. `/v1/chat/completions` relays an upstream event-stream verbatim, and
  `/swarm/run` streams from the assigned node (`executor.open_stream` /
  `iter_chunks` / `stream_job`; settlement on a successful open). `text/event-stream`,
  framed by `Connection: close`.
- **Sharding-backend presets** (`presets.py`, `edgemesh presets`): nine one-command
  setups — **exo, vLLM+Ray, Petals, llama.cpp-RPC, GPUStack, Ray Serve, SGLang,
  TGI, NVIDIA NIM** — each with its default `/v1`, a start hint, a docs link, and an
  honest `multi_machine` flag (exo/vLLM+Ray/… span machines; TGI/NIM are single-node
  multi-GPU). `edgemesh node <coordinator> --preset exo` registers a sharding node
  with the right endpoint in one go.
- Tests for streaming relay + presets (49 tests total).

## [0.5.0] — 2026-06-13

The "run a model no single device can hold" release: sharding-backend routing +
execution failover.

### Added
- **Sharding node type** (`NodeInfo.sharding`): a node can declare it fronts a
  runtime that splits one model across machines (exo / Petals / vLLM+Ray /
  llama.cpp RPC). The scheduler **exempts sharding nodes from the per-node VRAM
  filter**, so an oversized model routes to one automatically. Register with
  `edgemesh node <coordinator> --sharding --serve-url <exo/vLLM /v1>`.
- **Execution failover** in `run_job`: candidates are tried best-first; a node that
  errors is penalized (reputation down) and the job fails over to the next-best
  node (up to `max_attempts`), with per-attempt reporting.
- Scheduler `ranked()` (best-first eligible nodes) shared by scheduling + failover;
  single-fit nodes are preferred over sharding nodes for models that fit.
- Tests: oversized-model → sharding-node routing, and failover past a dead node
  (44 tests total).

### Honest scope
edgemesh now **routes to and executes against** a sharding backend; the tensor-level
split itself is performed by that backend (exo/Petals/vLLM+Ray), not by edgemesh.

## [0.4.0] — 2026-06-13

The "distributed execution" release: the swarm now actually *runs* work, not just
schedules it.

### Added
- **`executor.py`** — distributed execution + result aggregation over the mesh:
  - `run_job`: schedule a job → forward the OpenAI request to the assigned node's
    backend → return the result → settle credits + reputation. End-to-end.
  - `scatter_gather`: fan a batch of prompts across eligible nodes concurrently and
    aggregate (`first` | `concat` | `vote` | `all`). Genuine data-parallel inference.
  - `needs_sharding`: detect a model that fits no single node and route to a
    sharding-capable backend instead of faking pipeline parallelism.
- Gateway **`/swarm/run`** (single distributed job) and **`/swarm/map`** (scatter-gather).
- CLI: **`edgemesh run`** (run a distributed job) and `edgemesh node --serve-url`
  (advertise this node's reachable `/v1` endpoint so it can execute work; auto-
  discovered when omitted).
- Tests against a mock OpenAI backend over a real socket (42 tests total).

### Honest scope
Tensor-level **model sharding** (one model split layer-by-layer across machines)
is delegated to a sharding-capable backend (exo / Petals / vLLM+Ray / llama.cpp
RPC) registered as a node — edgemesh routes to it; it does not reimplement
pipeline parallelism. See README status table and ROADMAP.

## [0.3.0] — 2026-06-13

The "swarm" release: a decentralized-compute control plane on top of the mesh —
turn many devices into one orchestrated supercompute swarm.

### Added
- **Swarm control plane** (`swarm.py` + gateway `/swarm/*`): a node registry with
  trust **classes A/B/C**, a **scheduler**, a **credits + reputation ledger**, and
  **privacy-aware routing** (data sensitivity → minimum node class).
- **`protocol.py`**: transport-agnostic wire types (`NodeInfo`, `Job`,
  `Assignment`, hardware profile, trust classes, data-sensitivity levels) and
  HMAC-signed, short-lived bearer tokens.
- **`profile.py`**: node hardware profiler classifying the accelerator into
  Apple MLX / NVIDIA CUDA / AMD ROCm / CPU-only.
- **`scheduler.py`**: privacy gate → VRAM-fit filter → reputation/price auction.
- **`ledger.py`**: compute-credits settlement + reputation (deliberately an
  internal accounting unit, **not** a tradeable/crypto token — see DISCLAIMER).
- **CLI**: `edgemesh node <coordinator>` (join as a compute node with a class) and
  `edgemesh swarm` (view nodes + ledger). Gateway now runs the swarm control plane.
- Tests for protocol/ledger/scheduler/swarm + an end-to-end `/swarm` round-trip
  (36 tests total).

## [0.2.0] — 2026-06-13

The "universal cluster" release: from a meshing gateway to a full local-AI
control surface that any device or OS can join.

### Added
- **Numbered interactive menu** (`edgemesh menu`) wiring every capability.
- **Guided setup wizard** (`edgemesh setup`): detects hardware, discovers
  backends, offers to register the Cognis fleet, recommends fitting models.
- **Hardware detection** (`edgemesh hardware`, `hardware.py`): cross-OS CPU/RAM
  and NVIDIA/AMD/Apple GPU + VRAM probing, all best-effort and dependency-free.
- **Model catalog + fit-to-cluster** (`edgemesh catalog`, `catalog.py`): a
  curated catalog with rough VRAM footprints; recommends models that fit the
  detected budget. **Censorship toggle** via an `uncensored` flag / `--no-uncensored`.
- **Model download manager** (`edgemesh pull`, `manager.py`): drives `ollama pull`
  or the Hugging Face CLI; degrades gracefully when a tool isn't installed.
- **Clustering** (`edgemesh join`, `cluster.py` + gateway `/cluster/register`,
  `/cluster/nodes`): make any device a node; its backends merge into one
  coordinator catalog. Localhost URLs are re-advertised to a reachable address.
- **One-command Cognis fleet registration** (`edgemesh fleet`).
- **Native installers**: `install.sh` (Linux/macOS, pipx or venv) and
  `install.ps1` (Windows).
- **Deploy assets**: `Dockerfile`, `docker-compose.yml`, a systemd unit, and
  `deploy/README.md` for cloud/edge/anywhere.
- **Interop matrix** documenting 15 inference runtimes (`docs/INTEROP.md`).
- Tests for all new modules incl. an end-to-end cluster-register round-trip
  (25 tests total).

### Changed
- Gateway now doubles as a cluster coordinator.
- CLI grew `fleet`, `hardware`, `catalog`, `pull`, `join`, `setup`, `menu`,
  `version` alongside the existing `discover`/`add`/`models`/`backends`/`serve`.

## [0.1.0] — 2026-06-12
- Initial release: backend discovery, unified `/v1/models` catalog,
  `backend::model` routing, and an OpenAI-compatible gateway. Stdlib-only.
