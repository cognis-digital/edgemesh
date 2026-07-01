"""Onion relay crypto edge cases: sealed-box roundtrip, layer isolation, padding,
guard selection, key derivation, the circuit hop cap, and fail-closed behavior."""

from __future__ import annotations

import json

import pytest

from edgemesh import relay
from edgemesh.limits import MAX_CIRCUIT_HOPS

crypto = pytest.mark.skipif(not relay.HAVE_CRYPTO, reason="cryptography not installed")


# --- padding (no crypto needed) ----------------------------------------------
def test_pad_multiple_of_bucket():
    for data in (b"", b"x", b"hello", b"a" * 3000, b"b" * 4096):
        padded = relay.pad(data, bucket=2048)
        assert len(padded) % 2048 == 0


def test_pad_unpad_lossless():
    for data in (b"", b"\x00\x01\x02", b"unicode\xc3\xa9", b"x" * 10000):
        assert relay.unpad(relay.pad(data)) == data


def test_pad_empty_still_reaches_bucket():
    assert len(relay.pad(b"")) == 2048


def test_pad_custom_bucket():
    assert len(relay.pad(b"hi", bucket=64)) == 64


def test_pad_exactly_full_bucket_no_extra():
    # framed length = 4 + payload; if that lands on a bucket boundary, no extra pad
    payload = b"z" * (2048 - 4)
    assert len(relay.pad(payload, bucket=2048)) == 2048


# --- guard selection (no crypto needed) --------------------------------------
def test_select_guards_deterministic():
    relays = [(f"http://r{i}", f"{i:064x}") for i in range(8)]
    assert relay.select_guards(relays, 3) == relay.select_guards(list(reversed(relays)), 3)


def test_select_guards_bounded():
    relays = [(f"http://r{i}", f"{i:064x}") for i in range(2)]
    assert len(relay.select_guards(relays, 5)) == 2  # can't exceed available


def test_select_guards_min_one():
    relays = [(f"http://r{i}", f"{i:064x}") for i in range(3)]
    assert len(relay.select_guards(relays, 0)) == 1  # floor of 1


# --- fail-closed when crypto missing -----------------------------------------
def test_require_raises_when_no_crypto(monkeypatch):
    monkeypatch.setattr(relay, "HAVE_CRYPTO", False)
    with pytest.raises(relay.RelayUnavailable):
        relay._require()


def test_gen_keypair_fails_closed(monkeypatch):
    monkeypatch.setattr(relay, "HAVE_CRYPTO", False)
    with pytest.raises(relay.RelayUnavailable):
        relay.gen_keypair()


# --- sealed box (needs crypto) -----------------------------------------------
@crypto
def test_keypair_shapes():
    priv, pub = relay.gen_keypair()
    assert len(bytes.fromhex(priv)) == 32 and len(bytes.fromhex(pub)) == 32


@crypto
def test_public_for_matches_gen():
    priv, pub = relay.gen_keypair()
    assert relay.public_for(priv) == pub


@crypto
def test_seal_unseal_roundtrip():
    priv, pub = relay.gen_keypair()
    ct = relay.seal(pub, b"top secret")
    assert relay.unseal(priv, ct) == b"top secret"


@crypto
def test_seal_is_nondeterministic():
    _, pub = relay.gen_keypair()
    assert relay.seal(pub, b"same") != relay.seal(pub, b"same")  # fresh ephemeral+nonce


@crypto
def test_wrong_key_cannot_unseal():
    _, pub = relay.gen_keypair()
    other_priv, _ = relay.gen_keypair()
    ct = relay.seal(pub, b"secret")
    with pytest.raises(Exception):
        relay.unseal(other_priv, ct)


@crypto
def test_tampered_ciphertext_fails():
    priv, pub = relay.gen_keypair()
    ct = relay.seal(pub, b"secret")
    raw = bytearray(relay._unb64(ct))
    raw[-1] ^= 0xFF  # flip a ciphertext bit
    with pytest.raises(Exception):
        relay.unseal(priv, relay._b64(bytes(raw)))


# --- onion construction ------------------------------------------------------
@crypto
def test_build_onion_empty_circuit_raises():
    with pytest.raises(ValueError):
        relay.build_onion([], "http://backend", {})


@crypto
def test_build_onion_single_hop_is_exit():
    priv, pub = relay.gen_keypair()
    blob = relay.build_onion([("http://r0", pub)], "http://backend", {"messages": []})
    layer = json.loads(relay.unpad(relay.unseal(priv, blob)))
    assert layer["deliver"] == "http://backend"


@crypto
def test_build_onion_multihop_middle_reveals_next_hop_only():
    ks = [relay.gen_keypair() for _ in range(3)]
    circuit = [("http://r0", ks[0][1]), ("http://r1", ks[1][1]), ("http://r2", ks[2][1])]
    blob = relay.build_onion(circuit, "http://backend", {"m": 1})
    # entry relay peels one layer -> learns only next hop, not the backend
    layer0 = json.loads(relay.unpad(relay.unseal(ks[0][0], blob)))
    assert layer0["next"] == "http://r1" and "deliver" not in layer0


@crypto
def test_build_onion_enforces_hop_cap():
    # REGRESSION: MAX_CIRCUIT_HOPS was advertised but never enforced.
    circuit = [(f"http://r{i}", relay.gen_keypair()[1]) for i in range(MAX_CIRCUIT_HOPS + 1)]
    with pytest.raises(ValueError) as exc:
        relay.build_onion(circuit, "http://backend", {})
    assert str(MAX_CIRCUIT_HOPS) in str(exc.value)


@crypto
def test_build_onion_at_hop_cap_is_allowed():
    circuit = [(f"http://r{i}", relay.gen_keypair()[1]) for i in range(MAX_CIRCUIT_HOPS)]
    blob = relay.build_onion(circuit, "http://backend", {})
    assert isinstance(blob, str) and blob


@crypto
def test_build_cover_onion_respects_cap():
    circuit = [(f"http://r{i}", relay.gen_keypair()[1]) for i in range(MAX_CIRCUIT_HOPS + 2)]
    with pytest.raises(ValueError):
        relay.build_cover_onion(circuit)


@crypto
def test_cover_onion_marked_and_padded():
    priv, pub = relay.gen_keypair()
    blob = relay.build_cover_onion([("http://r0", pub)])
    layer = json.loads(relay.unpad(relay.unseal(priv, blob)))
    assert layer["payload"]["_cover"] is True
