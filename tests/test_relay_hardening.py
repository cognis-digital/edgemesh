"""Relay hardening: traffic padding, guard selection, broadened backend discovery,
and the Ed25519-signed relay directory."""

from __future__ import annotations

import pytest

from edgemesh import relay
from edgemesh.backends import KNOWN_PORTS


# --- no-crypto-needed pieces -------------------------------------------------
def test_pad_roundtrip_and_fixed_bucket():
    for data in (b"", b"x", b"hello world", b"a" * 5000):
        padded = relay.pad(data, bucket=2048)
        assert len(padded) % 2048 == 0          # fixed-size buckets
        assert relay.unpad(padded) == data       # lossless


def test_select_guards_is_stable_and_bounded():
    relays = [(f"http://r{i}", f"{i:064x}") for i in range(10)]
    g1 = relay.select_guards(relays, n=3)
    g2 = relay.select_guards(list(reversed(relays)), n=3)
    assert len(g1) == 3 and g1 == g2            # deterministic regardless of input order


def test_backend_discovery_broadened():
    names = set(KNOWN_PORTS.values())
    assert {"lmstudio", "jan", "sglang", "exo", "ollama"} <= names


# --- signed relay directory (needs cryptography) -----------------------------
crypto = pytest.mark.skipif(not relay.HAVE_CRYPTO, reason="cryptography not installed")


@crypto
def test_signed_directory_accepts_valid_rejects_tampered():
    from edgemesh import relay_dir
    apriv, apub = relay_dir.gen_authority()
    d = relay_dir.RelayDirectory(apub)
    _, onion_pub = relay.gen_keypair()
    d.add({"relay_id": "r1", "endpoint": "http://10.0.0.1:8780", "public_key": onion_pub}, apriv)
    assert d.verified_relays() == [("http://10.0.0.1:8780", onion_pub)]
    # tamper a descriptor after signing -> dropped
    d.entries[0]["descriptor"]["endpoint"] = "http://evil:8780"
    assert d.verified_relays() == []


@crypto
def test_directory_rejects_wrong_authority():
    from edgemesh import relay_dir
    apriv, _ = relay_dir.gen_authority()
    _, other_pub = relay_dir.gen_authority()
    d = relay_dir.RelayDirectory(other_pub)        # client trusts a DIFFERENT authority
    d.add({"relay_id": "r1", "endpoint": "http://x:8780", "public_key": "ab"}, apriv)
    assert d.verified_relays() == []               # signature won't verify
