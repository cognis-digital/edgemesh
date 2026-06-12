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

from edgemesh.registry import BackendRegistry
from edgemesh.router import NoBackendError, Router


def _catalog_as_openai(registry: BackendRegistry) -> dict:
    data = [
        {"id": model, "object": "model", "owned_by": ",".join(owners)}
        for model, owners in sorted(registry.model_catalog().items())
    ]
    return {"object": "list", "data": data}


def make_handler(registry: BackendRegistry) -> type[BaseHTTPRequestHandler]:
    router = Router(registry)

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
            else:
                self._send(404, {"error": {"message": f"not found: {self.path}"}})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/chat/completions":
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

    return Handler


def serve(registry: BackendRegistry, host: str = "127.0.0.1", port: int = 8780) -> None:
    """Run the gateway until interrupted."""
    server = ThreadingHTTPServer((host, port), make_handler(registry))
    print(f"edgemesh gateway on http://{host}:{port}  ({len(registry.names())} backend(s))")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        server.shutdown()


__all__ = ["serve", "make_handler"]
