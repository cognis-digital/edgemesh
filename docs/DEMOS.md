# Demos

Five runnable scenarios in [`../demos/`](../demos/), each targeting a different
audience. Every scenario uses **bundled offline fixtures** — in-process stub
backends and a snapshot swarm — so they run with no models loaded and no network.

```bash
PYTHONUTF8=1 python demos/run_all.py        # all five, end to end
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

---

Each demo prints narrated output and exits 0, so they double as smoke tests —
`tests/test_demos.py` runs every scenario's `main()` under `pytest`.
