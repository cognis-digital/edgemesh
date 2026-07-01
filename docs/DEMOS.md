# Demos

Twenty runnable scenarios in [`../demos/`](../demos/), each targeting a different
audience or layer. Every scenario uses **bundled offline fixtures** — in-process
stub backends and a snapshot swarm — so they run with no models loaded and no
network. Each prints narrated output and exits 0.

```bash
PYTHONUTF8=1 python demos/run_all.py        # all twenty, end to end
PYTHONUTF8=1 python demos/03_swarm_scheduling.py  # or just one
```

(`PYTHONUTF8=1` only matters on Windows consoles; elsewhere it is a harmless
no-op.)

## 1. Unify backends — *one catalog, one endpoint*
**Audience:** platform engineers.
Three OpenAI-compatible backends (the Cognis fleet, Ollama) are merged into one
catalog. A model served by several backends becomes a failover set automatically;
`Router.resolve` picks the backend, honors explicit `backend::model` pins, and
fails cleanly when nobody serves the model.

## 2. Fit models to hardware — *what will actually run here*
**Audience:** solo devs and hobbyists.
Turn a VRAM budget (8 GB GPU, 16 GB laptop, 64 GB Apple unified) into a curated,
biggest-first shortlist, filterable by modality or with uncensored fine-tunes
hidden. The demo also detects the real machine it runs on and recommends for it.

## 3. Swarm scheduling — *privacy, fit, auction*
**Audience:** distributed-systems teams.
A heterogeneous swarm (trusted A100 box, private Mac Studio, public laptop, exo
sharding cluster) runs the full job lifecycle: the **privacy gate** keeps a
confidential job on Class A only, the **VRAM fit** filters out the small laptop
(but exempts the sharding node), the **reputation/price auction** picks the
winner, and the **ledger** settles credits and moves reputation.

## 4. Privacy relay — *each hop sees only the next hop*
**Audience:** privacy-conscious users.
Build a 3-hop onion locally and peel it layer by layer: each relay learns only
the next hop; the exit learns the destination but not the origin. Honest about
what it is (real layered encryption) and isn't (not Tor-grade anonymity). If the
optional `cryptography` package is missing it **fails closed** and says so — and
still exits 0.

## 5. Live gateway — *a real /v1 round-trip, observed*
**Audience:** ops and compliance.
Stand up the actual edgemesh gateway in front of a bundled in-process backend and
drive real HTTP: `GET /v1/models`, `POST /v1/chat/completions` (routed and
relayed verbatim), and `GET /metrics` (Prometheus). The append-only audit log
shows the metadata-only compliance trail — prompt/response content is never
recorded.

## 6. Router failover — *a model on two backends survives a dead node*
**Audience:** SREs.
Two real in-process backends serve the same model. `Router.candidates` returns the
failover order the executor walks, and an explicit `backup::model` pin proves the
second backend answers when the primary is gone. Redundancy is free.

## 7. Distributed execution — *schedule → run → fail over → settle*
**Audience:** distributed-inference builders.
`run_job` schedules onto the best node, forwards the OpenAI request, and settles
credits + reputation. A broken node is deliberately ranked first so the demo shows
a live failover to the healthy node — the consumer pays only who delivered, and the
flaky node is penalized.

## 8. Scatter / gather — *data-parallel inference across the swarm*
**Audience:** batch/throughput users.
`scatter_gather` fans a batch of prompts across eligible nodes concurrently and
aggregates four ways: `all`, `first`, `concat`, and `vote` (self-consistency over
N replicas). Genuine data parallelism — not model sharding.

## 9. Credits + reputation — *the internal accounting unit (not a token)*
**Audience:** anyone reasoning about the economics.
Walks a funded consumer through several settlements, shows overdraw protection, and
demonstrates reputation converging to its floor/ceiling. Credits are conserved on
transfer — deliberately **not** a tradeable cryptocurrency.

## 10. Sharding presets — *route a model too big for one box*
**Audience:** large-model operators.
Lists the one-command sharding-backend presets (exo, vLLM+Ray, Petals, llama.cpp
RPC, …) and shows the scheduler exempting a `--sharding` node from the single-node
VRAM filter so a 70B job that fits nowhere still lands.

## 11. Multi-tenant auth + audit — *API keys on top of the gateway*
**Audience:** platform/security teams.
Turns on a keystore (keys stored hashed, shown once), drives the protected
`/swarm/run` endpoint with and without a key (401 vs pass-through), and prints the
metadata-only audit trail. Opt-in and dependency-free.

## 12. Rate limiting + caps — *one caller can't exhaust the network*
**Audience:** operators.
Drives the token-bucket limiter through a burst and a timed refill on a
deterministic virtual clock, shows per-caller isolation, and prints the hard caps
(body size, map batch, relay hops).

## 13. Streaming + metered billing — *pay for tokens actually produced*
**Audience:** billing/product.
Feeds a synthetic OpenAI SSE stream through `StreamMeter` (delta counting and an
explicit-usage override) and `metered_stream`, which settles on the tokens that
actually flowed — billing runs in a `finally` block, so a client disconnect still
pays for output.

## 14. Cluster join — *a device registers its backends with the coordinator*
**Audience:** anyone building a multi-device mesh.
Two devices join an in-process coordinator over real HTTP; each advertises
localhost backends rewritten to a reachable host and namespaced by node. The
coordinator's single `/v1` catalog then spans the cluster; the merge tolerates
malformed entries.

## 15. Signed relay directory — *verify every relay before trusting it*
**Audience:** privacy/security users.
A directory authority signs relay descriptors (Ed25519); a client verifies every
signature, and a post-signing tamper drops the forged entry. Needs the optional
`cryptography` dep; fails closed and still exits 0 without it.

## 16. Privacy gate — *data sensitivity decides who may compute*
**Audience:** compliance/privacy.
Runs the same job at public / private / confidential over one heterogeneous swarm
and shows the eligible set shrink — a confidential job can never land on a public
community node. The gate runs first, before fit and price.

## 17. Metrics / observability — *Prometheus scrape from the real gateway*
**Audience:** ops.
Drives a few requests through the real gateway and prints the `GET /metrics`
exposition: labeled request counters plus live gauges for backends, swarm nodes,
and ledger credits. Standard-library only, no client dependency.

## 18. Editor integration — *edgemesh in VSCode / Copilot / Cline / Continue*
**Audience:** developers.
Generates the ready-to-use MCP + Continue configs (`edgemesh vscode`), writes them
to a temp project, and shows the Continue provider pointed at the gateway's `/v1`.
The editor's agent gains edgemesh's models and its developer toolbelt via MCP.

## 19. Error handling — *fail loudly, legibly, and safely*
**Audience:** everyone.
Walks the error paths — an unserved model, a job that fits nowhere, a ledger
overdraw, an over-length relay circuit, and an empty circuit — showing each returns
a clear value or typed exception instead of a mystery crash.

## 20. End to end — *every layer, one job, start to finish*
**Audience:** the capstone tour.
A three-class swarm registers, a funded consumer submits a **private** job, the
privacy gate + VRAM fit + reputation auction pick a node, the executor runs it
against a real in-process backend, and the ledger settles credits and reputation —
one narrative through the whole stack.

---

Each demo prints narrated output and exits 0, so they double as smoke tests —
`tests/test_demos.py` runs every scenario's `main()` under `pytest`.
