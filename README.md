# edgemesh

**One model catalog and one `/v1` endpoint across every inference backend you run — on any OS.**

You probably have models running in more than one place: the Cognis local fleet
(uncensored / coding / vision), an Ollama server, a llama.cpp or vLLM box, maybe
a hosted API. `edgemesh` discovers them, aggregates their models into a single
catalog, and exposes one OpenAI-compatible gateway that routes each request to
the backend that can serve it. Point any OpenAI client at edgemesh and reach the
whole mesh.

Pure standard library — runs anywhere Python 3.10+ runs (Linux, macOS, Windows).

## Install

```bash
pip install "git+https://github.com/cognis-digital/edgemesh.git"
```

## Quick start

```bash
# Find local backends (Cognis fleet on 8772-8774, Ollama on 11434, etc.) and save them
edgemesh discover --save

# Register anything else (a remote box, a hosted endpoint)
edgemesh add my-vllm http://10.0.0.5:8000 --save

# See the unified catalog (model -> which backends serve it)
edgemesh models

# Run the gateway
edgemesh serve --port 8780
```

Then talk to the whole mesh through one endpoint:

```bash
curl http://127.0.0.1:8780/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "coding", "messages": [{"role": "user", "content": "hi"}]}'
```

Routing: edgemesh sends the request to the first backend that lists the model.
Force a specific backend with `backend::model` syntax (e.g.
`"model": "uncensored-fleet::uncensored"`).

## As a library

```python
from edgemesh.registry import BackendRegistry
from edgemesh.router import Router

reg = BackendRegistry()
reg.discover_local()                 # probe the local fleet + Ollama + llama.cpp
backend, upstream_model = Router(reg).resolve("coding")
```

## Interoperability, honestly stated

edgemesh **interoperates with** — it is not derived from — these projects. It
speaks their public OpenAI-compatible HTTP APIs and ships none of their code:

- **Cognis local fleet** (uncensored / coding / vision) and `cognis-code`
- **Ollama**, **llama.cpp**, **vLLM**, **LM Studio**, and any OpenAI-compatible server
- **exo** and other distributed-inference runtimes, when they expose a `/v1` endpoint

If a backend exposes `GET /v1/models` and `POST /v1/chat/completions`, edgemesh
can mesh it. No forks, no rebrands — just the wire protocol.

## License

Cognis Open Collaboration License (COCL) 1.0 — source-available; free for
non-commercial use, commercial use requires a separate license. See
[LICENSE](LICENSE).
