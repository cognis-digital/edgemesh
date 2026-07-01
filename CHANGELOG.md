# Changelog

All notable changes to edgemesh are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions use SemVer.

## [0.13.1] — 2026-07-01

Depth + hardening release: 4× the test suite (96 → 384 test functions, plus demo
smoke tests), 4× the runnable demos (5 → 20), and two real robustness fixes.

### Fixed
- **Relay circuit hop cap now enforced.** `limits.MAX_CIRCUIT_HOPS` (6) was
  documented and advertised (in the wizard and docs) as a DoS / loop guard but was
  never actually checked. `relay.build_onion` — the single construction point that
  `send_via_circuit` and `build_cover_onion` both route through — now raises a clear
  `ValueError` naming the cap when a circuit exceeds it. No public API change.
- **`NodeInfo.from_dict` no longer crashes on a partial profile.** A registration
  payload with a missing or incomplete `profile` raised a raw
  `TypeError: HardwareProfile.__init__() missing 3 required positional arguments`
  deep in the request handler. It now fills the three required identity fields
  (`os`/`arch`/`accelerator`) with safe defaults so a malformed node deserializes
  cleanly and is then rejected by the hardware floor with a legible error. Full
  profiles behave exactly as before.

### Added
- ~290 new tests across router failover, hardware fit, swarm scheduling/auction/
  ledger, onion relay crypto (incl. the hop-cap regression test), gateway/metrics
  error paths, protocol tokens, auth, MCP, limits, and executor failover.
- 15 new offline demos (`06`–`20`): router failover, distributed execution,
  scatter/gather, credits+reputation, sharding presets, auth+audit, rate limiting,
  streaming+metered billing, cluster join, signed relay directory, privacy gate,
  metrics observability, editor integration, error handling, and an end-to-end tour.

## [0.13.0] — 2026-06-19

The "developer agent + VSCode" release — edgemesh stops being just a gateway and
becomes a place you write code, on your own models.

### Added
- **Developer toolbelt** (`devtools.py`): a sandboxed, pure-stdlib `Toolbelt` —
  read/write/edit files, `find_files`, `grep`, `run` (shell), `run_tests`
  (auto-detects pytest/npm/go/cargo), and git (`status/diff/log/add/commit/
  branch/checkout/show`). Path operations are confined to the workspace root;
  every shell/git call is timed out and output-truncated. Exposed as both
  OpenAI tool specs (`openai_tools()`) and MCP descriptors (`mcp_tools()`).
- **Coding agent** (`agent.py`): a senior-engineer think→act→verify loop that
  drives any tool-calling model behind the gateway through the toolbelt.
  `edgemesh agent "<task>"` — runs on the local fleet / cluster, not the cloud.
- **MCP server** (`mcp_server.py`): newline-delimited JSON-RPC 2.0 over stdio
  (`edgemesh mcp`). Exposes the toolbelt plus `edgemesh_agent` and
  `edgemesh_chat`, so GitHub Copilot agent mode, Cline, Cursor, Continue and
  Claude get edgemesh's tools **and** models. No third-party MCP SDK.
- **VSCode integration configs** (`integrations.py` + `edgemesh vscode [--write]`):
  generates `.vscode/mcp.json`, `.mcp.json`, and `.continue/config.json`.
- **VSCode extension** (`edgemesh-vscode/`, TypeScript): chat sidebar (streaming),
  *Run Coding Agent on a Task*, AI commit messages from the staged diff,
  *Explain Selection*, and one-click MCP/VSCode setup.
- New CLI commands: `agent`, `mcp`, `tools`, `vscode`.
- 18 new tests (devtools / agent / MCP) — **90 total**.

### Notes
- The gateway already forwards `tools`/`tool_choice` verbatim, so OpenAI
  tool-calling works through edgemesh for any backend that supports it.

## [0.12.0] — 2026-06-13

The "observability + Helm" release — what an ops/platform team needs to run it.

### Added
- **Prometheus `/metrics`** (`metrics.py`): stdlib counter store + text exposition
  format; per-route `edgemesh_requests_total` plus live gauges (`edgemesh_backends`,
  `edgemesh_swarm_nodes`, `edgemesh_models_cataloged`, `edgemesh_ledger_credits_total`).
  No client-library dependency.
- **Helm chart** (`deploy/helm/edgemesh/`): Deployment + Service + health probes +
  Prometheus scrape annotations; `values.yaml` for image/replicas/resources/extraArgs
  (e.g. `--auth --audit`)/persistence. `helm install edgemesh deploy/helm/edgemesh`.
- Tests for metric rendering + the `/metrics` endpoint (72 total).

## [0.11.0] — 2026-06-13

The "sovereign / enterprise adoption" release — the controls a regulated or defense
buyer asks for first, so edgemesh can be a private, on-prem, OpenAI-compatible AI
platform on hardware you own.

### Added
- **API-key access control** (`auth.py`): per-tenant keys, stored **hashed** (shown once),
  `Bearer` auth on the privileged endpoints. Opt-in (`serve --auth`); open if no keys.
  `edgemesh key add <name>` / `key list`.
- **Append-only audit log** (`audit.py`): JSONL of privileged actions — who/what/when/
  outcome — **metadata only, never prompt/response content**, so the trail isn't an
  exfiltration surface. `serve --audit`; ship it to a SIEM/WORM store.
- **Adoption docs**: `docs/USE_CASES.md` (the sovereign/air-gapped problem it solves +
  buyer scenarios + a 5-minute on-prem pilot), `SECURITY.md` (model + hardening
  checklist + reporting), `THREAT_MODEL.md` (assets, mitigations, explicit non-goals).
- Tests for keystore (hashing/verify/roundtrip), audit (metadata-only), and the gateway
  auth gate (401 without key, audited) — 70 tests total.

## [0.10.0] — 2026-06-13

The "relay hardening + run-anywhere" release.

### Added
- **Relay hardening** toward stronger anonymity: fixed-bucket **traffic padding** (layer
  sizes no longer leak circuit position), **guard selection** (stable pinned entry hops),
  optional **per-hop jitter**, a **cover-traffic** onion builder, and an **Ed25519-signed
  relay directory** (`relay_dir.py`) so clients verify every relay descriptor against a
  trusted authority before building a circuit.
- **Broadened backend discovery** ("all backends compatible"): auto-probe LM Studio
  (1234), Jan (1337), SGLang (30000), exo (52415), text-generation-webui (5000),
  KoboldCpp (5001) alongside the Cognis fleet, Ollama, llama.cpp, and the vLLM/Ray/TGI/
  NIM port. With the exo / vLLM+Ray presets, sharded execution against a live cluster is
  fully wired (register it as a `--sharding` node; oversized jobs route there).
- **Deploy anywhere**: Kubernetes manifests (`deploy/k8s/edgemesh.yaml`, Deployment +
  Service + health probes) and package-manager install notes (brew/winget/pipx).
- Tests for padding, guards, broadened discovery, and signed-directory verify/tamper
  (65 tests total).

### Honest scope
The relay is materially harder to deanonymize now, but still not a guarantee against a
global passive adversary — see DISCLAIMER.md.

## [0.9.0] — 2026-06-13

The "comprehensive setup" release.

### Added
- **Guided multi-step setup wizard** (`edgemesh setup`, rewritten): role selection
  (all-in-one / coordinator / node / relay), a **hardware check against the minimum
  policy** (below-floor / relay-only / inference), backend discovery + Cognis fleet,
  model fit + optional pull, an mTLS offer, a privacy-relay offer, a sharding-preset
  suggestion for under-spec devices, an abuse-limits summary, and **tailored
  next-step commands** for the chosen role.
- Decision logic factored into pure, tested helpers (`hardware_verdict`, `next_steps`);
  60 tests total.

## [0.8.0] — 2026-06-13

The "minimum hardware + anti-abuse" release.

### Added
- **Minimum-hardware policy** (`limits.py`): a join floor (~2 GB RAM — relay/participant)
  and an inference-capability gate (8 GB RAM for CPU/Apple-unified, ≥4 GB VRAM for a
  discrete GPU). `/swarm/register` rejects below-floor nodes and reports
  `inference_capable`, so under-spec devices can still relay but aren't handed jobs
  they can't run.
- **Abuse protections**: a thread-safe **token-bucket rate limiter** per client IP on
  `/swarm/run`, `/swarm/map`, `/relay/forward`, `/v1/chat/completions`; a **1 MB request
  body cap** (413); a **64-prompt cap** on scatter-gather; and a **6-hop cap** on relay
  circuits (loop/DoS guard).
- Tests for admission + the limiter (58 tests total).

## [0.7.0] — 2026-06-13

The "security + privacy" release: mutual TLS, token-metered billing, and an
onion-style community relay.

### Added
- **Mutual TLS** (`security/mtls.py`): `server_context`/`client_context` (stdlib
  `ssl`, `CERT_REQUIRED`), an openssl-based dev PKI generator, `edgemesh gen-certs`,
  and `edgemesh serve --tls` — only client-cert-authenticated peers may connect.
- **Token-metered stream settlement** (`executor.StreamMeter`, `metered_stream`):
  streams now settle on **tokens actually produced** (explicit `usage` when present,
  else content-delta count) instead of on open; settlement runs in `finally`, so a
  client disconnect still bills for what was generated.
- **Onion-style privacy relay** (`relay.py`, optional `edgemesh[relay]`): route a
  request through a circuit of community relays with one X25519+AES-GCM encryption
  layer per hop, so no single relay sees both ends. `edgemesh gen-relay-key`,
  `edgemesh serve --relay-key`, gateway `/relay/info` + `/relay/forward`. Fails
  closed without `cryptography` — never a fake/insecure fallback.
- **Dense, Mermaid-rich README** (architecture, request lifecycle, onion circuit).
- 55 tests total (mTLS handshake, token metering, 3-hop circuit delivery).

### Honest scope
The relay is real layered-encryption multi-hop routing, **not** Tor-grade anonymity
(no traffic mixing / timing resistance / cover traffic / large anonymity set), and
not for evading the law or relaying abuse. See DISCLAIMER.md.

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
