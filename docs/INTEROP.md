# Interoperability matrix

edgemesh **interoperates with** other runtimes over their public
OpenAI-compatible HTTP APIs — it ships none of their code and is not derived
from them. If a backend exposes `GET /v1/models` and `POST /v1/chat/completions`,
edgemesh can mesh it. This page summarizes the landscape (researched 2026-06; the
default ports and "pull" mechanisms below are from each project's public docs —
verify against the live docs, as they change).

| Runtime | OpenAI `/v1`? | Default port | Model download | Multi-node | OSes |
|---|---|---|---|---|---|
| **Cognis fleet** (uncensored/coding/vision) | yes | 8772–8774 | n/a (pre-loaded) | via edgemesh | Win/Linux/macOS |
| **Ollama** | yes | 11434 | `ollama pull` / `POST /api/pull` (streaming, resumable) | single host | Win/Linux/macOS |
| **llama.cpp** (`llama-server`) | yes | 8080 | GGUF path / `-hf` flag | RPC backend | Win/Linux/macOS |
| **vLLM** | yes | 8000 | HF id at launch | tensor + pipeline (Ray) | Linux |
| **LM Studio** | yes | 1234 | GUI / `lms` CLI | single host | Win/Linux/macOS |
| **GPUStack** | yes (`/v1-openai`) | 80 | catalog deploy (auto-download) | yes (heterogeneous) | Win/Linux/macOS |
| **Petals** | needs adapter | n/a | HF shards | yes (swarm) | Linux/macOS |
| **Ray Serve (LLM)** | yes | ~8000 | engine downloads by HF id | yes (native) | Linux |
| **LocalAI** | yes | 8080 | `POST /models/apply` (gallery) | P2P (maturity varies) | Win/Linux/macOS (Docker) |
| **Jan** (Cortex) | yes | 1337 / 8000 | GUI / Cortex CLI | single stack | Win/Linux/macOS |
| **KoboldCpp** | yes | ~5001 | GGUF path | single host | Win/Linux/macOS |
| **text-generation-webui** | yes (`--api`) | 5000 | GUI downloader | single host | Win/Linux/macOS |
| **SGLang** | yes | 30000 | HF id at launch | yes (TP/PP) | Linux |
| **Hugging Face TGI** | yes (Messages API) | 80→8080 | `--model-id` at launch | multi-GPU | Linux (Docker) |
| **NVIDIA NIM** | yes | 8000 | per-model container (NGC) | multi-GPU / K8s | Linux + NVIDIA |

## Notes
- **Cleanest "pull any model" HTTP APIs** are Ollama (`/api/pull`) and LocalAI
  (`/models/apply`); these are the first targets for edgemesh's planned
  pull-to-a-remote-node feature. Most other runtimes treat the model as a launch
  parameter, so a model change means (re)launching that backend.
- **Native distributed/sharding** runtimes (relevant to "fit a big model to the
  cluster"): exo, GPUStack, vLLM (+Ray), Ray Serve, SGLang, Petals, llama.cpp RPC.
  edgemesh complements these — it federates *across* whatever you run, rather than
  sharding a single model itself.
- **exo** (exo-explore/exo) is the closest sibling: it clusters heterogeneous
  devices and exposes OpenAI/Claude/Ollama APIs (port 52415). edgemesh meshes it
  like any other `/v1` backend rather than reimplementing it.

> Sources: project docs for each runtime (Ollama, llama.cpp, vLLM, LM Studio,
> GPUStack, Petals, Ray Serve, LocalAI, Jan, KoboldCpp, text-generation-webui,
> SGLang, Hugging Face TGI, NVIDIA NIM) and the exo repository. Figures were
> compiled from public documentation; confirm exact ports/flags against the
> current upstream docs before relying on them.
