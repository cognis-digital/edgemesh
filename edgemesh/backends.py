"""Backend definitions and discovery for edgemesh.

A *backend* is any OpenAI-compatible inference endpoint -- the Cognis local
fleet (uncensored / coding / vision), an Ollama server, a llama.cpp server, a
remote vLLM/TGI box, or a hosted API. edgemesh treats them uniformly: it probes
``{base_url}/v1/models`` to learn which models each one serves.

Discovery makes "hook it up to everything" a one-liner: probe a set of local
ports and register whatever answers.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field

# Local ports edgemesh probes by default. The Cognis fleet lives on 8772-8774;
# 11434 is Ollama's default; 8080/8000 are common llama.cpp / vLLM defaults.
KNOWN_PORTS: dict[int, str] = {
    8774: "uncensored-fleet",
    8772: "coding-fleet",
    8773: "vision-fleet",
    11434: "ollama",
    8080: "llamacpp",
    8000: "openai-compatible",
}


@dataclass
class Backend:
    """One OpenAI-compatible inference endpoint."""

    name: str
    base_url: str
    models: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "base_url": self.base_url.rstrip("/"), "models": list(self.models)}

    @classmethod
    def from_dict(cls, data: dict) -> "Backend":
        return cls(name=data["name"], base_url=data["base_url"].rstrip("/"), models=list(data.get("models", [])))

    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/models"

    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/chat/completions"


def parse_models(payload: object) -> list[str]:
    """Extract model ids from an OpenAI ``/v1/models`` response body.

    Tolerates both the OpenAI shape ``{"data": [{"id": ...}]}`` and a bare list.
    """
    if isinstance(payload, dict):
        data = payload.get("data", [])
    elif isinstance(payload, list):
        data = payload
    else:
        return []
    ids: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
        elif isinstance(item, str):
            ids.append(item)
    return sorted(set(ids))


def probe(base_url: str, timeout: float = 4.0) -> list[str] | None:
    """Return the models a backend serves, or ``None`` if it is unreachable."""
    url = f"{base_url.rstrip('/')}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception:
        return None
    return parse_models(payload)


def discover(host: str = "127.0.0.1", ports: dict[int, str] | None = None,
             timeout: float = 4.0) -> list[Backend]:
    """Probe ``host`` on each known port and return the backends that answer."""
    ports = ports or KNOWN_PORTS
    found: list[Backend] = []
    for port, name in ports.items():
        models = probe(f"http://{host}:{port}", timeout=timeout)
        if models is not None:
            found.append(Backend(name=name, base_url=f"http://{host}:{port}", models=models))
    return found
