"""edgemesh -- a cross-OS federated gateway that unifies every OpenAI-compatible
inference backend (the Cognis fleet, Ollama, llama.cpp, vLLM, hosted APIs) behind
one model catalog and one /v1 endpoint."""

from edgemesh.backends import Backend, discover, parse_models, probe
from edgemesh.registry import BackendRegistry
from edgemesh.router import NoBackendError, Router

__version__ = "0.3.0"

__all__ = [
    "Backend",
    "BackendRegistry",
    "Router",
    "NoBackendError",
    "discover",
    "probe",
    "parse_models",
    "__version__",
]
