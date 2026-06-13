# edgemesh

**One model catalog and one `/v1` endpoint across every inference backend you
run — on any OS, across any number of devices.**

You probably have models running in more than one place: the Cognis local fleet
(uncensored / coding / vision), an Ollama server, a llama.cpp or vLLM box, maybe
a hosted API. `edgemesh` discovers them, aggregates their models into a single
catalog, and exposes one OpenAI-compatible gateway that routes each request to
the backend that can serve it. Point any OpenAI client at edgemesh and reach the
whole mesh — and let any other device **join** that mesh with one command.

Pure standard library. Runs anywhere Python 3.10+ runs (Linux, macOS, Windows),
in Docker, on a cloud VM, or on an edge box.

## Install

```bash
# Linux / macOS
./install.sh
# Windows (PowerShell)
./install.ps1
# or straight from pip
pip install "git+https://github.com/cognis-digital/edgemesh.git"
```

## Two ways to drive it

```bash
edgemesh setup     # guided first-run wizard (detects hardware, finds backends)
edgemesh menu      # numbered interactive menu for everything below
```

…or use the commands directly.

## Connect your backends

```bash
edgemesh discover --save        # probe localhost (Cognis fleet, Ollama, llama.cpp, …)
edgemesh fleet --save           # one-shot: register the Cognis fleet (8772-8774, 11434)
edgemesh add my-vllm http://10.0.0.5:8000 --save   # any OpenAI-compatible endpoint
edgemesh backends               # what's registered
edgemesh models                 # unified catalog: model -> which backends serve it
```

## Fit & download models to your hardware

```bash
edgemesh hardware               # CPU/RAM/GPU/VRAM + the model-fit budget
edgemesh catalog                # curated models that fit THIS machine (largest first)
edgemesh catalog --no-uncensored  # hide uncensored/abliterated fine-tunes
edgemesh pull qwen2.5-7b        # download via the right tool (ollama / huggingface-cli)
```

`catalog` carries an `uncensored` flag on community abliterated models, so you can
toggle censored vs uncensored model selection. edgemesh drives whatever backend
tooling is installed and tells you how to get it if it's missing.

## Run the gateway

```bash
edgemesh serve --port 8780
curl http://127.0.0.1:8780/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "coding", "messages": [{"role": "user", "content": "hi"}]}'
```

Routing: edgemesh sends the request to the first backend that lists the model.
Force a specific one with `backend::model` (e.g. `"uncensored-fleet::uncensored"`).

## Build a cluster across devices

```bash
# coordinator (note its LAN IP)
edgemesh serve
# any other device, any OS:
edgemesh join http://<coordinator-ip>:8780
```

Each node discovers its local backends and registers them with the coordinator,
whose single `/v1` catalog then spans the whole mesh. See
[`deploy/README.md`](deploy/README.md) for Docker, systemd, and cloud.

## As a library

```python
from edgemesh.registry import BackendRegistry
from edgemesh.router import Router

reg = BackendRegistry(); reg.discover_local()
backend, upstream_model = Router(reg).resolve("coding")
```

## Interoperability, honestly stated

edgemesh **interoperates with** — it is not derived from — other runtimes. It
speaks their public OpenAI-compatible HTTP APIs and ships none of their code:
the Cognis fleet, Ollama, llama.cpp, vLLM, LM Studio, GPUStack, LocalAI, Jan,
KoboldCpp, text-generation-webui, SGLang, Hugging Face TGI, NVIDIA NIM, and exo
(when it exposes `/v1`). Full matrix: [`docs/INTEROP.md`](docs/INTEROP.md). No
forks, no rebrands — just the wire protocol.

## Docs
- [`CHANGELOG.md`](CHANGELOG.md) · [`ROADMAP.md`](ROADMAP.md) · [`docs/INTEROP.md`](docs/INTEROP.md) · [`deploy/README.md`](deploy/README.md)

## License

Cognis Open Collaboration License (COCL) 1.0 — source-available; free for
non-commercial use, commercial use requires a separate license. See
[LICENSE](LICENSE).
