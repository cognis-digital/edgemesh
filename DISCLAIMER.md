# Disclaimer & scope

## Compute credits are not a cryptocurrency or a security

edgemesh's swarm includes a **credits + reputation ledger** so nodes can earn
credit for completing jobs and consumers can spend credit to run them. This is an
**internal accounting unit**. edgemesh deliberately does **not** implement:

- a transferable / on-chain token,
- an exchange or any buy/sell/stake-for-profit mechanism,
- any representation that credits are an investment or will appreciate.

Turning credits into a real, tradeable token is a separate product decision with
**securities, money-transmission, tax, and consumer-protection implications** that
vary by jurisdiction. That is a decision for the operator and their legal counsel —
it is intentionally out of scope for this software.

## Transports

The swarm's communication layer is designed as a pluggable software seam (HTTP/TLS
today; LAN/mesh/other adapters are roadmap). Operating any licensed radio spectrum
is the operator's responsibility and must comply with applicable regulations;
edgemesh ships no capability to do so.

## Privacy relay (onion routing)

The optional relay routes requests through multiple community relays with one
encryption layer per hop, so a single relay cannot link the requester to the
compute node. Be clear-eyed about what this is:

- It **is** real layered encryption + multi-hop routing that defeats a single
  curious/compromised relay.
- It is **not** Tor-grade anonymity — there is no traffic mixing, timing-analysis
  resistance, cover traffic, padding, or a large anonymity set. A global passive
  adversary, or correlation across entry+exit, can still deanonymize.
- It is for **privacy in a community compute network**. It is **not** for evading
  law enforcement, hiding illegal activity, or relaying abuse. Relay operators are
  responsible for their jurisdiction's rules; run a relay only if you accept that.
- Encryption requires the `cryptography` package; without it the relay refuses to
  operate (fails closed) rather than sending anything unprotected.

## Operation

You are responsible for the security, lawfulness, and acceptable use of any swarm
you run, and for the data your nodes process. Run public (Class C) nodes only on
hardware and networks you control and are willing to share.
