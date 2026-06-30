# Architecture

edgemesh has two layers that build on each other. The **gateway** unifies every
OpenAI-compatible backend you run behind one model catalog and one `/v1`
endpoint. The **swarm** grows that into a trust-tiered, scheduled, credit-metered,
optionally onion-routed compute network. The core is pure standard library
(Python 3.10+); two features are opt-in extras (mTLS dev certs, the privacy
relay's `cryptography`).

## The whole picture

```mermaid
flowchart TB
    client([OpenAI client / edgemesh CLI])

    subgraph CP["Control plane — the gateway"]
        GW["/v1 gateway<br/>gateway.py"]
        RT["router.py<br/>model -> backend"]
        REG["registry.py<br/>BackendRegistry + catalog"]
        SW["swarm.py<br/>SwarmController"]
        SCH["scheduler.py<br/>privacy · fit · auction"]
        LED["ledger.py<br/>credits + reputation"]
        OBS["metrics.py · audit.py<br/>Prometheus + JSONL"]
    end

    subgraph NODES["Swarm of nodes — any OS / device"]
        A["Class A · trusted"]
        B["Class B · private"]
        C["Class C · public"]
        SH["sharding node<br/>exo / vLLM+Ray / Petals"]
    end

    subgraph RELAY["Privacy relay circuit — optional"]
        R1[relay 1] --> R2[relay 2] --> R3["relay 3 (exit)"]
    end

    client -->|chat / models| GW
    GW --- RT --- REG
    GW --- SW --- SCH --- LED
    GW --- OBS
    SCH -->|dispatch| A & B & C
    SCH -->|oversized model| SH
    client -.->|private request| R1
    R3 -.->|deliver| C
    classDef hot stroke:#f4b400,stroke-width:3px;
    class GW,SCH hot;
```

## Components

### Backends & discovery (`edgemesh/backends.py`)
A *backend* is any OpenAI-compatible endpoint — the Cognis fleet, Ollama,
llama.cpp, vLLM/TGI, a hosted API. `probe()` reads `{base_url}/v1/models` to learn
what it serves; `discover()` sweeps a set of known local ports (8772–8774 fleet,
11434 Ollama, 8080 llama.cpp, 8000 vLLM, …) and registers whatever answers.

### Registry & catalog (`edgemesh/registry.py`, `edgemesh/catalog.py`)
`BackendRegistry` holds backends by name and computes the **aggregated model
catalog** — a map of `model -> [backends that serve it]`. A model served by more
than one backend is automatically a failover set. `catalog.py` is a separate
curated list of open-weight models with rough VRAM footprints, used to *fit a
model to the hardware* a node actually has.

### Router (`edgemesh/router.py`)
Resolves a requested model to a `(backend, upstream_model)` pair. Explicit
`backend::model` pins win; otherwise the first backend (by name) that lists the
model is chosen, with `candidates()` giving the full failover order.

### Swarm control plane (`edgemesh/swarm.py`, `edgemesh/protocol.py`)
`SwarmController` is the in-memory orchestration core: a **node registry** (each
`NodeInfo` carries trust class, `HardwareProfile`, reputation), `register` /
`heartbeat` / `prune` for membership, and `submit` / `complete` for jobs.
`protocol.py` is the JSON-serializable wire contract plus HMAC short-lived bearer
tokens.

### Scheduler (`edgemesh/scheduler.py`)
Three gates, in order:

```mermaid
flowchart LR
    job[Job + data_class] --> P{Privacy gate<br/>min trust class}
    P -->|allowed classes| F{Capability fit<br/>usable VRAM}
    F -->|sharding node exempt| AU{Auction<br/>reputation / price}
    AU --> win[Winning Assignment]
    classDef g stroke:#23d160,stroke-width:2px;
    class P,F,AU g;
```

1. **Privacy** — `confidential -> Class A only`, `private -> A/B`, `public -> any`.
2. **Fit** — the node needs enough `usable_vram_mb()`; sharding nodes (exo /
   vLLM+Ray / Petals / llama.cpp RPC) span machines and are exempt.
3. **Auction** — among the eligible, `reputation / price` wins (single-fit nodes
   slightly preferred over sharding for models that fit on one box).

### Ledger (`edgemesh/ledger.py`)
Compute **credits** (consumers spend, nodes earn) and **reputation** (success
`×1.05`, failure `×0.80`, clamped). This is an internal accounting unit — **not**
a cryptocurrency, token, or tradeable security, deliberately.

### Privacy relay (`edgemesh/relay.py`)
Onion-style multi-hop relaying: the client wraps a request in one X25519 +
AES-GCM layer per hop, each padded to a fixed bucket. Each relay peels exactly one
layer and learns only the next hop; the exit delivers to the compute node. It
**fails closed** without the optional `cryptography` package — never a fake
fallback — and is honest that it is not Tor-grade anonymity.

### Gateway, metrics & audit (`edgemesh/gateway.py`, `metrics.py`, `audit.py`)
A stdlib `http.server` that serves `GET /v1/models` (aggregated catalog),
`POST /v1/chat/completions` (routed + relayed verbatim, with streaming), the
`/swarm/*` and `/cluster/*` endpoints, `GET /metrics` (Prometheus text format),
and an append-only **metadata-only** audit log (prompt/response content is never
recorded).

## Data model

```mermaid
erDiagram
    BACKEND ||--o{ MODEL : serves
    REGISTRY ||--o{ BACKEND : holds
    SWARM ||--o{ NODEINFO : tracks
    NODEINFO ||--|| HARDWAREPROFILE : has
    SWARM ||--o{ ASSIGNMENT : schedules
    ASSIGNMENT }o--|| NODEINFO : "runs on"
    LEDGER ||--o{ ACCOUNT : "credits + reputation"
    BACKEND { string name string base_url list models }
    NODEINFO { string node_id string node_class string endpoint float reputation bool sharding }
    HARDWAREPROFILE { string os string accelerator int ram_mb int vram_mb }
    ASSIGNMENT { string job_id string node_id float price list shards }
```

## Why these choices

- **Standard library core.** Runs anywhere Python 3.10+ runs — no daemon to
  operate, nothing leaving your machine. The two heavier features (mTLS, relay
  crypto) are opt-in extras.
- **One catalog, many backends.** A model on two backends is a failover set for
  free; the router and gateway just pick.
- **Privacy is a gate, not a bolt-on.** Data sensitivity decides which nodes may
  even be considered, before fit or price.
- **Honest about limits.** The relay says plainly it is not Tor-grade anonymity;
  credits say plainly they are not a token.
