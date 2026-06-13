"""A minimal OpenAI-compatible gateway that fronts every registered backend.

Endpoints:
  GET  /v1/models             aggregated catalog across all backends
  POST /v1/chat/completions   routed to the backend that serves the model
  GET  /healthz               liveness

Pure standard library (http.server + urllib), so it runs anywhere Python does.
Forwarding is transparent: the upstream JSON response is streamed back verbatim.
"""

from __future__ import annotations

import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from edgemesh.cluster import register_into
from edgemesh.executor import run_job, scatter_gather
from edgemesh.ledger import Ledger
from edgemesh.protocol import Job, NodeInfo
from edgemesh.registry import BackendRegistry
from edgemesh.router import NoBackendError, Router
from edgemesh.swarm import SwarmController


def _catalog_as_openai(registry: BackendRegistry) -> dict:
    data = [
        {"id": model, "object": "model", "owned_by": ",".join(owners)}
        for model, owners in sorted(registry.model_catalog().items())
    ]
    return {"object": "list", "data": data}


def make_handler(registry: BackendRegistry,
                 swarm: SwarmController | None = None) -> type[BaseHTTPRequestHandler]:
    router = Router(registry)
    nodes: dict[str, dict] = {}  # node name -> {address, backends}
    swarm = swarm or SwarmController()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:  # quiet by default
            pass

        def do_GET(self) -> None:
            if self.path.rstrip("/") == "/v1/models":
                self._send(200, _catalog_as_openai(registry))
            elif self.path.rstrip("/") == "/healthz":
                self._send(200, {"status": "ok", "backends": registry.names()})
            elif self.path.rstrip("/") == "/cluster/nodes":
                self._send(200, {"nodes": nodes})
            elif self.path.rstrip("/") == "/swarm/nodes":
                self._send(200, {"nodes": [n.to_dict() for n in swarm.list_nodes()]})
            elif self.path.rstrip("/") == "/swarm/ledger":
                self._send(200, swarm.ledger.to_dict())
            else:
                self._send(404, {"error": {"message": f"not found: {self.path}"}})

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}

        def do_POST(self) -> None:
            route = self.path.rstrip("/")
            if route == "/cluster/register":
                self._register()
                return
            if route == "/swarm/register":
                node = swarm.register(NodeInfo.from_dict(self._body()))
                self._send(200, {"ok": True, "node_id": node.node_id,
                                 "reputation": node.reputation, "swarm_size": len(swarm.nodes)})
                return
            if route == "/swarm/submit":
                b = self._body()
                job = Job.new(b.get("model", ""), data_class=b.get("data_class", "public"),
                              min_vram_mb=int(b.get("min_vram_mb", 0)), modality=b.get("modality", "text"),
                              submitted_by=b.get("consumer", ""))
                a = swarm.submit(job, price=float(b.get("price", 1.0)))
                if not a:
                    self._send(409, {"error": {"message": "no eligible node for this job"}})
                else:
                    self._send(200, {"job_id": a.job_id, "node_id": a.node_id, "price": a.price})
                return
            if route == "/swarm/complete":
                b = self._body()
                self._send(200, swarm.complete(b.get("job_id", ""), b.get("consumer", ""),
                                                bool(b.get("success", True))))
                return
            if route == "/swarm/run":
                b = self._body()
                job = Job.new(b.get("model", ""), data_class=b.get("data_class", "public"),
                              min_vram_mb=int(b.get("min_vram_mb", 0)), submitted_by=b.get("consumer", ""))
                res = run_job(swarm, job, {"messages": b.get("messages", [])},
                              b.get("consumer", ""), price=float(b.get("price", 1.0)))
                self._send(200 if res.get("ok") else 409, res)
                return
            if route == "/swarm/map":
                b = self._body()
                res = scatter_gather(swarm, b.get("model", ""), b.get("prompts", []),
                                     aggregate=b.get("aggregate", "all"),
                                     data_class=b.get("data_class", "public"),
                                     min_vram_mb=int(b.get("min_vram_mb", 0)))
                self._send(200 if res.get("ok") else 409, res)
                return
            if route != "/v1/chat/completions":
                self._send(404, {"error": {"message": f"not found: {self.path}"}})
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw or b"{}")
                model = body["model"]
            except (json.JSONDecodeError, KeyError):
                self._send(400, {"error": {"message": "invalid request: missing 'model'"}})
                return
            try:
                backend, upstream_model = router.resolve(model)
            except NoBackendError as exc:
                self._send(404, {"error": {"message": str(exc)}})
                return
            body["model"] = upstream_model
            forward = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                backend.chat_url(), data=forward,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    payload = json.loads(resp.read().decode("utf-8", "replace"))
                self._send(200, payload)
            except Exception as exc:  # upstream failure -> 502
                self._send(502, {"error": {"message": f"backend {backend.name} failed: {exc}"}})

        def _register(self) -> None:
            """A cluster node registers its backends with this coordinator."""
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": {"message": "invalid JSON"}})
                return
            added = register_into(registry, payload)
            node = payload.get("node", "unknown")
            nodes[node] = {"address": payload.get("address"), "backends": added}
            self._send(200, {"ok": True, "node": node, "added": added,
                             "catalog_size": len(registry.model_catalog())})

    return Handler


def serve(registry: BackendRegistry, host: str = "127.0.0.1", port: int = 8780,
          swarm: SwarmController | None = None) -> None:
    """Run the gateway + swarm control plane until interrupted."""
    swarm = swarm or SwarmController(Ledger.load())
    server = ThreadingHTTPServer((host, port), make_handler(registry, swarm))
    print(f"edgemesh gateway + swarm control plane on http://{host}:{port}  "
          f"({len(registry.names())} backend(s))")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        server.shutdown()
        swarm.ledger.save()


__all__ = ["serve", "make_handler"]
