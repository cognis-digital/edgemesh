# Why edgemesh — the problem it solves

Organizations want the capability of large AI models **without sending their data
to someone else's cloud**, and without buying a single monolithic GPU server. They
already own heterogeneous compute — workstations, a few GPU boxes, Apple Silicon
laptops, an on-prem rack. edgemesh turns that into **one sovereign, private,
OpenAI-compatible AI platform** they fully control.

## The core problem

> *"We can't use hosted AI — our data can't leave the building. But we can't run the
> models we need on any one machine we own, and we have no way to pool what we have."*

edgemesh answers exactly that: discover every backend you run, present one `/v1`
endpoint, schedule and run jobs across the fleet, shard a model too big for one box
across machines, and keep **all data inside your perimeter** — with the controls a
regulated or defense buyer requires.

## Who it's for

| Buyer | Problem | What edgemesh gives them |
|---|---|---|
| **Defense / government (on-prem, disconnected, classified-adjacent)** | No cloud AI; air-gapped networks; strict audit | Fully **offline** operation, **mTLS** between nodes, per-tenant **API keys**, **append-only audit log**, no telemetry/phone-home |
| **Regulated enterprise** (finance, healthcare, legal) | Data residency / privacy law; can't ship prompts to a vendor | Private inference on owned hardware; **content is never logged**; access control + audit for compliance |
| **Edge / field / expeditionary** | Intermittent or no connectivity; mixed hardware | Runs on CPU/Apple/NVIDIA/AMD; **minimum-hardware admission**; nodes join/leave; failover |
| **Research labs / universities** | Idle GPUs scattered across the org | Pool them into one swarm; **credits + reputation** to share fairly; **sharding** for big models |
| **Privacy-sensitive teams** | Don't want any single node to see who asked what | **Onion-style relay** (community or internal) so requests are unlinkable to a single relay |

## What makes it adoptable

- **Sovereign & air-gapped:** stdlib core, no outbound calls, no telemetry. It runs
  where your data already lives.
- **Meets you where your hardware is:** Apple MLX / NVIDIA CUDA / AMD ROCm / CPU, any OS,
  Docker, Kubernetes, systemd — `edgemesh setup` walks the operator through it.
- **Interoperates, doesn't lock in:** speaks the OpenAI wire protocol to Ollama, vLLM,
  llama.cpp, LM Studio, exo, TGI, NIM, and more. Bring the models and runtimes you want.
- **The controls buyers ask for first:** mTLS, API keys, audit logging, rate limiting,
  minimum-hardware admission — all opt-in, documented in [SECURITY.md](../SECURITY.md)
  and [THREAT_MODEL.md](../THREAT_MODEL.md).

## A 5-minute on-prem pilot

```bash
./install.sh
edgemesh gen-certs                       # dev mTLS PKI
edgemesh key add analytics-team          # issue a tenant key
edgemesh serve --tls --auth --audit      # private, authenticated, audited gateway
# point any OpenAI client at https://<host>:8780/v1 with the bearer key
```
That's a sovereign private-AI endpoint on hardware you own, with auth and an audit
trail, in five minutes — the thing the cloud can't give a data-restricted buyer.
