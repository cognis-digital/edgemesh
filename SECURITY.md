# Security

## Reporting a vulnerability

Email security@cognisdigital.com (or open a private security advisory on the repo).
Please include repro steps and affected version. We aim to acknowledge within a few
business days. Do not file public issues for vulnerabilities.

## Supported versions

edgemesh is pre-1.0 and ships from `main`; security fixes land on the latest minor.
Pin a tag for reproducibility and watch the [CHANGELOG](CHANGELOG.md).

## Security model (what's built in)

| Control | What it does | How to enable |
|---|---|---|
| **Mutual TLS** | Only client-cert-authenticated peers reach a gateway | `edgemesh gen-certs` → `serve --tls` |
| **API keys** | Per-tenant auth; keys stored **hashed**, shown once | `edgemesh key add <name>` → `serve --auth` |
| **Audit log** | Append-only JSONL of privileged actions (**metadata only**, no prompt/response content) | `serve --audit` |
| **Rate limiting** | Token-bucket per client IP on heavy endpoints | on by default |
| **Body / batch / hop caps** | 1 MB body, 64-prompt batch, 6-hop circuit | on by default (`limits.py`) |
| **Minimum-hardware admission** | Rejects under-spec nodes; gates inference vs relay | on by default |
| **Onion relay** | Layered encryption; **fails closed** without `cryptography` | `serve --relay-key` (`edgemesh[relay]`) |
| **No telemetry** | Core is stdlib; makes no outbound/phone-home calls | always |

## Hardening checklist (production / on-prem)

1. **Enable mTLS** between every node and the coordinator; issue certs from your own CA
   (the `gen-certs` PKI is for dev).
2. **Enable `--auth`** and issue one API key per tenant/service; rotate regularly.
3. **Enable `--audit`** and ship the log to your SIEM / a WORM store.
4. Bind the gateway to a trusted interface; put it behind your firewall / network policy.
   The gateway is **not** a substitute for network segmentation.
5. Only run **public (Class C)** nodes on hardware/networks you're willing to share;
   keep confidential workloads on **Class A** nodes (the privacy gate enforces this).
6. Treat compute **credits as an internal accounting unit**, not money — see
   [DISCLAIMER.md](DISCLAIMER.md).

## Scope notes

- The privacy relay raises the bar against a single curious relay; it is **not**
  anonymity against a global passive adversary (see [THREAT_MODEL.md](THREAT_MODEL.md)).
- edgemesh secures the *control plane and routing*; it does not sandbox the inference
  backends themselves — run those with your own isolation (containers/VMs).
