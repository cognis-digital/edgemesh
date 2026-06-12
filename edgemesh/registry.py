"""A persistable set of backends plus the aggregated model catalog."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from edgemesh.backends import Backend, discover

DEFAULT_CONFIG = str(Path.home() / ".edgemesh" / "config.json")


class BackendRegistry:
    """Holds backends keyed by name and answers "who serves model X?"."""

    def __init__(self, backends: list[Backend] | None = None) -> None:
        self._backends: dict[str, Backend] = {}
        for backend in backends or []:
            self.add(backend)

    def add(self, backend: Backend) -> None:
        """Add or replace a backend by name."""
        self._backends[backend.name] = backend

    def remove(self, name: str) -> None:
        self._backends.pop(name, None)

    def get(self, name: str) -> Backend:
        return self._backends[name]

    def names(self) -> list[str]:
        return sorted(self._backends)

    def backends(self) -> list[Backend]:
        return [self._backends[name] for name in self.names()]

    def model_catalog(self) -> dict[str, list[str]]:
        """Map each model id to the sorted list of backend names that serve it."""
        catalog: dict[str, list[str]] = {}
        for name in self.names():
            for model in self._backends[name].models:
                catalog.setdefault(model, [])
                if name not in catalog[model]:
                    catalog[model].append(name)
        return {model: sorted(names) for model, names in catalog.items()}

    # --- persistence -----------------------------------------------------
    def to_config(self) -> dict:
        return {"backends": [b.to_dict() for b in self.backends()]}

    @classmethod
    def from_config(cls, data: dict) -> "BackendRegistry":
        return cls([Backend.from_dict(b) for b in data.get("backends", [])])

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG) -> "BackendRegistry":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as handle:
            return cls.from_config(json.load(handle))

    def save(self, path: str = DEFAULT_CONFIG) -> None:
        """Persist the registry atomically (crash-safe)."""
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.to_config(), handle, indent=2, sort_keys=True)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def discover_local(self, host: str = "127.0.0.1", timeout: float = 4.0) -> list[str]:
        """Probe local ports and merge any backends found. Returns names added."""
        added: list[str] = []
        for backend in discover(host=host, timeout=timeout):
            self.add(backend)
            added.append(backend.name)
        return added
