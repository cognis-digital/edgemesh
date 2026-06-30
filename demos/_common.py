"""Shared helpers and offline fixtures for the demo scenarios.

Everything here is self-contained and works with **no network and no models
running**: the "backends" are tiny in-process stub servers (stdlib
``http.server``) that speak just enough of the OpenAI ``/v1`` API for the demos
to exercise edgemesh's real code paths. Nothing leaves the machine.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# allow `python demos/xx.py` (and `run_all.py`) from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgemesh.backends import Backend                 # noqa: E402
from edgemesh.protocol import (                        # noqa: E402
    CLASS_A, CLASS_B, CLASS_C, HardwareProfile, NodeInfo)
from edgemesh.registry import BackendRegistry          # noqa: E402


def rule(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


# --- bundled, offline "backend" fixtures -------------------------------------
# A snapshot of what three OpenAI-compatible endpoints would report from their
# /v1/models — exactly what `edgemesh.backends.probe()` returns at runtime, but
# frozen so the demos need nothing running.
FIXTURE_BACKENDS: list[Backend] = [
    Backend("uncensored-fleet", "http://127.0.0.1:8774",
            ["qwen3-8b-abliterated", "dolphin3-8b", "llama3.1-8b"]),
    Backend("coding-fleet", "http://127.0.0.1:8772",
            ["qwen2.5-coder-7b", "deepseek-r1-8b", "llama3.1-8b"]),
    Backend("ollama", "http://127.0.0.1:11434",
            ["llama3.1-8b", "mistral-7b", "nomic-embed-text"]),
]


def fixture_registry() -> BackendRegistry:
    """A registry pre-populated with the bundled backend snapshot (offline)."""
    return BackendRegistry(list(FIXTURE_BACKENDS))


# --- bundled swarm-node fixtures ---------------------------------------------
def _profile(accel: str, ram_mb: int, vram_mb: int | None, gpu: str,
             os_name: str = "Linux", arch: str = "x86_64") -> HardwareProfile:
    return HardwareProfile(os=os_name, arch=arch, accelerator=accel,
                           cpu_cores=16, ram_mb=ram_mb, vram_mb=vram_mb, gpu_name=gpu)


def fixture_nodes() -> list[NodeInfo]:
    """A heterogeneous, multi-OS swarm: a trusted A100 box, a private Mac, a
    public laptop, and a sharding cluster — the kinds of devices a real mesh
    would span."""
    return [
        NodeInfo("a100-dc-01", "datacenter-a100", CLASS_A, "https://dc-01:8443",
                 _profile("cuda", 256000, 80000, "NVIDIA A100 80GB")),
        NodeInfo("mac-studio-7", "alice-mac-studio", CLASS_B, "https://mac-7:8443",
                 _profile("mlx", 196000, None, "Apple M2 Ultra", os_name="Darwin", arch="arm64")),
        NodeInfo("laptop-pub-3", "community-laptop", CLASS_C, "http://laptop-3:8000",
                 _profile("cpu", 16000, None, "", os_name="Windows")),
        NodeInfo("shard-cluster", "exo-3x-mac-mini", CLASS_C, "http://exo:52415",
                 _profile("mlx", 64000, None, "3x Apple M4 (exo)", os_name="Darwin", arch="arm64"),
                 sharding=True),
    ]


# --- an in-process OpenAI-compatible stub backend ----------------------------
class _StubBackendHandler(BaseHTTPRequestHandler):
    MODELS: list[str] = []

    def log_message(self, *a):  # keep demo output clean
        pass

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self._json(200, {"object": "list",
                             "data": [{"id": m, "object": "model"} for m in self.MODELS]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        if self.path.rstrip("/") == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            model = req.get("model", "?")
            self._json(200, {
                "id": "chatcmpl-demo", "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant",
                                         "content": f"[stub:{model}] pong"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            })
        else:
            self._json(404, {"error": {"message": "not found"}})


@contextmanager
def stub_backend(models: list[str]):
    """Run an in-process OpenAI-compatible backend on a random port.

    Yields its ``http://127.0.0.1:<port>`` base URL. Used by the gateway demo to
    do a real round-trip with no external server.
    """
    handler = type("H", (_StubBackendHandler,), {"MODELS": list(models)})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
