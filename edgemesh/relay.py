"""Onion-style privacy relaying for the swarm — inspired by Tor, community-run.

A request can be routed through a *circuit* of volunteer relays so that no single
relay learns both who is asking and which compute node ultimately answers. Each
relay peels exactly one encryption layer, learning only the **next hop**; the
final (exit) relay delivers to the compute backend. Responses return synchronously
back along the same circuit.

Honesty about what this is and isn't
------------------------------------
This is a real layered-encryption multi-hop relay (X25519 sealed boxes + AES-GCM,
one layer per hop). It is **not** a guarantee of Tor-grade anonymity: there is no
traffic mixing, timing-analysis resistance, cover traffic, or large anonymity set
here. It raises the bar (a single relay can't deanonymize a request), it does not
make you anonymous against a global adversary. It is for **privacy in a community
compute network**, not for evading the law or relaying abuse.

Encryption is provided by the optional `cryptography` package (`pip install
edgemesh[relay]`). If it is missing, the relay **fails closed** — it does not fall
back to a fake/insecure scheme.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request

from edgemesh.limits import MAX_CIRCUIT_HOPS

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    HAVE_CRYPTO = True
except Exception:  # pragma: no cover - depends on environment
    HAVE_CRYPTO = False


class RelayUnavailable(RuntimeError):
    """Raised when relay crypto isn't installed (fails closed, never fakes it)."""


def _require():
    if not HAVE_CRYPTO:
        raise RelayUnavailable("relay encryption requires the 'cryptography' package: "
                               "pip install edgemesh[relay]")


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode())


# --- traffic padding (so layer sizes don't leak circuit position) -------------
PAD_BUCKET = 2048


def pad(data: bytes, bucket: int = PAD_BUCKET) -> bytes:
    """Length-prefix then zero-pad to the next `bucket` multiple."""
    framed = len(data).to_bytes(4, "big") + data
    target = ((len(framed) + bucket - 1) // bucket) * bucket
    return framed + b"\x00" * (target - len(framed))


def unpad(blob: bytes) -> bytes:
    n = int.from_bytes(blob[:4], "big")
    return blob[4:4 + n]


# --- keys --------------------------------------------------------------------
def gen_keypair() -> tuple[str, str]:
    """Return (private_hex, public_hex) for a relay identity."""
    _require()
    priv = X25519PrivateKey.generate()
    priv_b = priv.private_bytes(serialization.Encoding.Raw,
                                serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub_b = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                            serialization.PublicFormat.Raw)
    return priv_b.hex(), pub_b.hex()


def public_for(private_hex: str) -> str:
    _require()
    priv = X25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    return priv.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw).hex()


def _derive(shared: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"edgemesh-relay-v1").derive(shared)


# --- sealed box (encrypt to a relay's public key) ----------------------------
def seal(recipient_pub_hex: str, plaintext: bytes) -> str:
    """Encrypt to a recipient public key. Returns b64(ephemeral_pub || nonce || ct)."""
    _require()
    recipient = X25519PublicKey.from_public_bytes(bytes.fromhex(recipient_pub_hex))
    eph = X25519PrivateKey.generate()
    key = _derive(eph.exchange(recipient))
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    eph_pub = eph.public_key().public_bytes(serialization.Encoding.Raw,
                                             serialization.PublicFormat.Raw)
    return _b64(eph_pub + nonce + ct)


def unseal(private_hex: str, blob_b64: str) -> bytes:
    """Decrypt a sealed blob with a relay's private key."""
    _require()
    raw = _unb64(blob_b64)
    eph_pub, nonce, ct = raw[:32], raw[32:44], raw[44:]
    priv = X25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    key = _derive(priv.exchange(X25519PublicKey.from_public_bytes(eph_pub)))
    return AESGCM(key).decrypt(nonce, ct, None)


# --- onion construction (client side) ----------------------------------------
def build_onion(circuit: list[tuple[str, str]], deliver_endpoint: str, payload: dict) -> str:
    """Wrap `payload` in one encryption layer per hop.

    `circuit` is an ordered list of (relay_endpoint, relay_public_hex), entry first.
    The exit relay delivers to `deliver_endpoint` (a compute node's /v1 base). Each
    relay's layer reveals only the next hop. Returns the blob for the entry relay.
    """
    _require()
    if not circuit:
        raise ValueError("circuit must have at least one relay")
    if len(circuit) > MAX_CIRCUIT_HOPS:
        raise ValueError(
            f"circuit has {len(circuit)} hops, exceeding the {MAX_CIRCUIT_HOPS}-hop "
            "cap (limits.MAX_CIRCUIT_HOPS) — long circuits are a DoS / loop risk")
    # innermost: the exit relay is told to deliver. Each layer is padded to a fixed
    # bucket before sealing, so a relay can't infer its position from the size.
    _, exit_pub = circuit[-1]
    blob = seal(exit_pub, pad(json.dumps({"deliver": deliver_endpoint, "payload": payload}).encode()))
    # wrap outward: each relay learns only the next relay's endpoint + inner blob
    for i in range(len(circuit) - 2, -1, -1):
        next_endpoint = circuit[i + 1][0]
        _, pub = circuit[i]
        blob = seal(pub, pad(json.dumps({"next": next_endpoint, "blob": blob}).encode()))
    return blob


# --- relay node (server side) ------------------------------------------------
def handle_forward(private_hex: str, blob_b64: str, timeout: float = 300.0,
                   max_delay_ms: int = 0) -> dict:
    """Peel one layer and either forward to the next relay or deliver to a backend.

    `max_delay_ms` adds a small random per-hop delay (timing-correlation friction);
    0 disables it (used in tests).
    """
    _require()
    if max_delay_ms:
        import secrets
        import time
        time.sleep(secrets.randbelow(max_delay_ms + 1) / 1000.0)
    layer = json.loads(unpad(unseal(private_hex, blob_b64)))
    if "deliver" in layer:                       # exit relay -> call the compute node
        url = layer["deliver"].rstrip("/") + "/v1/chat/completions"
        body = json.dumps(layer["payload"]).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    # middle/entry relay -> pass the inner blob to the next relay, return its answer
    return _post_forward(layer["next"], layer["blob"], timeout)


def _post_forward(relay_endpoint: str, blob_b64: str, timeout: float = 300.0) -> dict:
    url = relay_endpoint.rstrip("/") + "/relay/forward"
    req = urllib.request.Request(url, data=json.dumps({"blob": blob_b64}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# --- client helper -----------------------------------------------------------
def select_guards(relays: list[tuple[str, str]], n: int = 3) -> list[tuple[str, str]]:
    """Pick a small, *stable* set of entry guards from (endpoint, pubkey) relays.

    Pinning a few guards (rather than a fresh random entry each circuit) is the Tor
    lesson: it bounds the chance that an adversary ever observes your entry hop.
    Deterministic by public key so a client keeps the same guards across runs;
    persist the result and reuse it.
    """
    return sorted(relays, key=lambda r: r[1])[:max(1, n)]


def build_cover_onion(circuit: list[tuple[str, str]]) -> str:
    """A padded dummy circuit, indistinguishable on the wire from a real one — send
    these on a jittered schedule as cover traffic. The exit no-op-delivers to itself."""
    _require()
    return build_onion(circuit, circuit[-1][0], {"_cover": True, "messages": []})


def fetch_relay(endpoint: str, timeout: float = 10.0) -> tuple[str, str]:
    """Ask a relay for its (endpoint, public_key) via GET /relay/info."""
    with urllib.request.urlopen(endpoint.rstrip("/") + "/relay/info", timeout=timeout) as resp:
        info = json.loads(resp.read())
    return endpoint, info["public_key"]


def send_via_circuit(relay_endpoints: list[str], deliver_endpoint: str, payload: dict,
                     timeout: float = 300.0) -> dict:
    """Build a circuit from relay endpoints and send a request through it."""
    _require()
    circuit = [fetch_relay(e) for e in relay_endpoints]
    blob = build_onion(circuit, deliver_endpoint, payload)
    return _post_forward(relay_endpoints[0], blob, timeout)
