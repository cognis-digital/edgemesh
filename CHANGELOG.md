# Changelog

All notable changes to edgemesh are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions use SemVer.

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
