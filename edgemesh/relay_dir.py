"""A signed relay directory — so clients can trust the list of relays.

A *directory authority* holds an Ed25519 keypair and signs each relay's descriptor
(id, endpoint, onion public key). Clients ship the authority's public key, fetch the
directory, and **verify every signature** before building a circuit — so a hostile
directory server can't inject relays it controls (a classic onion-routing attack).

Reuses the optional `cryptography` dep (shared with `relay.py`); fails closed.
"""

from __future__ import annotations

import json

from edgemesh.relay import HAVE_CRYPTO, RelayUnavailable

if HAVE_CRYPTO:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey)
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption)


def _require():
    if not HAVE_CRYPTO:
        raise RelayUnavailable("relay directory needs 'cryptography': pip install edgemesh[relay]")


def _canon(descriptor: dict) -> bytes:
    return json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()


def gen_authority() -> tuple[str, str]:
    """Return (authority_private_hex, authority_public_hex)."""
    _require()
    k = Ed25519PrivateKey.generate()
    return (k.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex(),
            k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex())


def sign_descriptor(authority_priv_hex: str, descriptor: dict) -> str:
    _require()
    k = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(authority_priv_hex))
    return k.sign(_canon(descriptor)).hex()


def verify_descriptor(authority_pub_hex: str, descriptor: dict, sig_hex: str) -> bool:
    _require()
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority_pub_hex))
    try:
        pub.verify(bytes.fromhex(sig_hex), _canon(descriptor))
        return True
    except (InvalidSignature, ValueError):
        return False


class RelayDirectory:
    """A set of authority-signed relay descriptors."""

    def __init__(self, authority_pub_hex: str) -> None:
        self.authority_pub = authority_pub_hex
        self.entries: list[dict] = []   # [{"descriptor": {...}, "sig": "..."}]

    def add(self, descriptor: dict, authority_priv_hex: str) -> None:
        self.entries.append({"descriptor": descriptor,
                             "sig": sign_descriptor(authority_priv_hex, descriptor)})

    def verified_relays(self) -> list[tuple[str, str]]:
        """Return (endpoint, onion_public_key) for entries with a valid signature."""
        out = []
        for e in self.entries:
            d = e.get("descriptor", {})
            if verify_descriptor(self.authority_pub, d, e.get("sig", "")):
                out.append((d["endpoint"], d["public_key"]))
        return out

    def to_json(self) -> str:
        return json.dumps({"authority": self.authority_pub, "entries": self.entries})

    @classmethod
    def from_json(cls, blob: str) -> "RelayDirectory":
        data = json.loads(blob)
        d = cls(data["authority"])
        d.entries = data.get("entries", [])
        return d
