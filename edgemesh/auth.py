"""API-key access control for the gateway — multi-tenant auth on top of mTLS.

mTLS proves *which machine* connects; API keys identify *which principal/tenant* is
making a request, so you can authorize and audit per user/team. Keys are stored
**hashed** (SHA-256) — the plaintext is shown once at creation and never persisted.

Auth is opt-in: with no keystore (or an empty one) the gateway is open, as before.
Turn it on with `edgemesh serve --auth` after `edgemesh key add <name>`.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from pathlib import Path

DEFAULT_KEYS = str(Path.home() / ".edgemesh" / "keys.json")


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class KeyStore:
    def __init__(self, keys: dict | None = None) -> None:
        # {key_hash: {"name": str, "scopes": [..]}}
        self.keys: dict[str, dict] = dict(keys or {})

    def add(self, name: str, scopes: list[str] | None = None) -> str:
        """Create a key, store only its hash, and return the plaintext ONCE."""
        plaintext = "em_" + secrets.token_urlsafe(32)
        self.keys[hash_key(plaintext)] = {"name": name, "scopes": scopes or ["*"]}
        return plaintext

    def verify(self, key: str) -> dict | None:
        """Return the principal record for a valid key, else None."""
        return self.keys.get(hash_key(key))

    def principal_from_header(self, authorization: str | None) -> dict | None:
        if not authorization:
            return None
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else authorization.strip()
        return self.verify(token)

    @property
    def enforced(self) -> bool:
        return bool(self.keys)

    # --- persistence ---------------------------------------------------------
    @classmethod
    def load(cls, path: str = DEFAULT_KEYS) -> "KeyStore":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def save(self, path: str = DEFAULT_KEYS) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.keys, fh, indent=2, sort_keys=True)
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
