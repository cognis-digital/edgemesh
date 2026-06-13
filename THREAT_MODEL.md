# Threat model

A concise, honest threat model for an edgemesh deployment. It states what edgemesh
defends against, how, and — just as importantly — what it does **not**.

## Assets
- **Prompt/response data** (often the most sensitive thing; must stay in-perimeter).
- **Model weights** held on nodes.
- **Compute** (don't let it be stolen/abused).
- **The credits + reputation ledger** (integrity of accounting).

## Trust boundaries
- Consumer ↔ gateway/control plane.
- Control plane ↔ compute nodes (any OS/owner; trust-tiered A/B/C).
- Node ↔ node (relay circuits).
- Coordinator ↔ relay directory authority.

## Threats & mitigations

| Threat | Mitigation | Residual risk |
|---|---|---|
| **Eavesdropping** on control/data traffic | mTLS (`--tls`) | None new if mTLS on; off by default |
| **Unauthorized requests** | API keys (`--auth`), hashed at rest | Key theft → rotate; scope keys |
| **Rogue/under-spec node** joins | Minimum-hardware admission; trust classes; reputation | A malicious Class-C node sees jobs routed to it — keep confidential work on Class A |
| **Confidential data → untrusted node** | Privacy gate: `confidential → Class A only`, `private → A/B` | Operator must classify nodes correctly |
| **Resource abuse / DoS** | Rate limiting, body/batch/hop caps | Distributed abuse needs network-layer defense too |
| **Hostile relay tries to deanonymize** | Onion layers (one hop's knowledge each), padding, guards, jitter | **Not** resistant to a global passive adversary or entry+exit correlation |
| **Malicious relay directory** injects relays | Ed25519-signed descriptors; clients verify vs a trusted authority key | Authority key compromise → re-key + redistribute |
| **Ledger tampering** | Server-authoritative; persisted atomically | Not Byzantine-fault-tolerant across mutually-distrusting coordinators (single coordinator of record) |

## Explicit non-goals
- **Not** global-adversary anonymity (the relay is privacy, not Tor-grade anonymity).
- **Not** a network firewall/segmentation replacement — deploy behind your network controls.
- **Not** a sandbox for the inference backends — isolate those yourself (containers/VMs).
- **Not** a cryptocurrency or financial system — credits are internal accounting
  ([DISCLAIMER.md](DISCLAIMER.md)).
- **Not** Byzantine consensus — one coordinator is the source of truth for its swarm.

## Recommended posture
mTLS + `--auth` + `--audit` on, gateway behind your firewall, confidential workloads
pinned to Class-A nodes you own, audit shipped to a SIEM. That covers the common
enterprise/defense threat set; the rest is your network and host security.
