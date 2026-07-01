"""KeyStore edge cases: scopes, hashing, header parsing, persistence, enforcement."""

from __future__ import annotations

from edgemesh.auth import KeyStore, hash_key


def test_hash_key_is_sha256_hex():
    h = hash_key("secret")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_hash_key_deterministic():
    assert hash_key("x") == hash_key("x")


def test_empty_keystore_not_enforced():
    assert KeyStore().enforced is False


def test_keystore_enforced_after_add():
    ks = KeyStore()
    ks.add("a")
    assert ks.enforced is True


def test_add_returns_plaintext_once():
    ks = KeyStore()
    key = ks.add("svc")
    assert key.startswith("em_")
    # only the hash is stored
    assert key not in ks.keys and hash_key(key) in ks.keys


def test_default_scope_is_wildcard():
    ks = KeyStore()
    key = ks.add("a")
    assert ks.verify(key)["scopes"] == ["*"]


def test_custom_scopes():
    ks = KeyStore()
    key = ks.add("a", scopes=["run", "map"])
    assert ks.verify(key)["scopes"] == ["run", "map"]


def test_verify_unknown_key_none():
    assert KeyStore().verify("em_nope") is None


def test_principal_from_bearer_header():
    ks = KeyStore()
    key = ks.add("svc")
    assert ks.principal_from_header(f"Bearer {key}")["name"] == "svc"


def test_principal_from_bearer_case_insensitive():
    ks = KeyStore()
    key = ks.add("svc")
    assert ks.principal_from_header(f"bEaReR {key}")["name"] == "svc"


def test_principal_from_raw_header():
    ks = KeyStore()
    key = ks.add("svc")
    assert ks.principal_from_header(key)["name"] == "svc"


def test_principal_from_none_header():
    assert KeyStore().principal_from_header(None) is None


def test_principal_from_invalid_header():
    ks = KeyStore()
    ks.add("svc")
    assert ks.principal_from_header("Bearer garbage") is None


def test_keystore_roundtrip(tmp_path):
    ks = KeyStore()
    key = ks.add("t", scopes=["run"])
    p = str(tmp_path / "keys.json")
    ks.save(p)
    reloaded = KeyStore.load(p)
    assert reloaded.verify(key)["scopes"] == ["run"]


def test_keystore_load_missing_is_empty(tmp_path):
    assert KeyStore.load(str(tmp_path / "none.json")).enforced is False


def test_multiple_keys_distinct():
    ks = KeyStore()
    k1 = ks.add("a")
    k2 = ks.add("b")
    assert ks.verify(k1)["name"] == "a" and ks.verify(k2)["name"] == "b"
    assert len(ks.keys) == 2
