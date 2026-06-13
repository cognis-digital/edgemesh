"""Turn any device into a node of one edgemesh cluster.

Model
-----
One node runs the **coordinator** (the gateway, ``edgemesh serve``). Every other
device runs ``edgemesh join <coordinator-url>``: it discovers the
OpenAI-compatible backends running locally, then registers them with the
coordinator over HTTP. The coordinator merges them into its registry, so its
single ``/v1`` catalog now spans the whole cluster — any OS, any device.

Because backends are just ``{name, base_url, models}``, a node's localhost URLs
are rewritten to an address the coordinator can actually reach (the node's
advertised host) before registering.

Pure standard library.
"""

from __future__ import annotations

import json
import socket
import urllib.request

from edgemesh.backends import Backend
from edgemesh.registry import BackendRegistry


def local_ip() -> str:
    """Best-effort routable IP for this host (no traffic actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _readvertise(backend: Backend, advertise_host: str) -> Backend:
    """Rewrite a localhost backend URL to one the coordinator can reach."""
    url = backend.base_url
    for needle in ("127.0.0.1", "localhost", "0.0.0.0"):
        if needle in url:
            url = url.replace(needle, advertise_host)
            break
    return Backend(name=backend.name, base_url=url, models=list(backend.models))


def join(coordinator_url: str, *, node_name: str | None = None,
         advertise_host: str | None = None, host: str = "127.0.0.1",
         timeout: float = 10.0) -> dict:
    """Discover this node's local backends and register them with the coordinator.

    Returns the coordinator's JSON response. Raises on transport failure.
    """
    node_name = node_name or socket.gethostname()
    advertise_host = advertise_host or local_ip()

    local = BackendRegistry()
    local.discover_local(host=host)
    backends = [_readvertise(b, advertise_host) for b in local.backends()]
    # Namespace each backend by node so two nodes' "ollama" don't collide.
    payload = {
        "node": node_name,
        "address": advertise_host,
        "backends": [
            {**b.to_dict(), "name": f"{node_name}.{b.name}"} for b in backends
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        coordinator_url.rstrip("/") + "/cluster/register",
        data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def register_into(registry: BackendRegistry, payload: dict) -> list[str]:
    """Coordinator side: merge a node's registration payload into the registry.

    Returns the names of backends added. Tolerant of malformed input.
    """
    added: list[str] = []
    for b in payload.get("backends", []):
        try:
            backend = Backend.from_dict(b)
        except (KeyError, TypeError):
            continue
        registry.add(backend)
        added.append(backend.name)
    return added
