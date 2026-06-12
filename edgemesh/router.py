"""Resolve a requested model to the backend that should serve it."""

from __future__ import annotations

from edgemesh.backends import Backend
from edgemesh.registry import BackendRegistry

# Explicit-routing separator: a request for "uncensored-fleet::llama3" forces
# that backend and forwards the bare model id "llama3".
EXPLICIT_SEP = "::"


class NoBackendError(LookupError):
    """Raised when no registered backend can serve the requested model."""


class Router:
    """Maps an incoming model name to a (Backend, upstream_model) pair."""

    def __init__(self, registry: BackendRegistry) -> None:
        self.registry = registry

    def resolve(self, model: str) -> tuple[Backend, str]:
        """Return the backend and the model id to send upstream.

        Resolution order:
          1. Explicit ``backend::model`` syntax wins.
          2. Otherwise the first backend (by name) that lists the model.
          3. Otherwise raise NoBackendError.
        """
        if EXPLICIT_SEP in model:
            backend_name, _, upstream = model.partition(EXPLICIT_SEP)
            if backend_name in self.registry.names():
                return self.registry.get(backend_name), upstream
            raise NoBackendError(f"unknown backend {backend_name!r} in {model!r}")

        serving = self.registry.model_catalog().get(model, [])
        if serving:
            return self.registry.get(serving[0]), model
        raise NoBackendError(f"no backend serves model {model!r}")

    def candidates(self, model: str) -> list[Backend]:
        """All backends that could serve ``model`` (for fallback), best first."""
        if EXPLICIT_SEP in model:
            name = model.split(EXPLICIT_SEP, 1)[0]
            return [self.registry.get(name)] if name in self.registry.names() else []
        return [self.registry.get(n) for n in self.registry.model_catalog().get(model, [])]
