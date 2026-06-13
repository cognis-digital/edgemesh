"""Prometheus metrics — the observability hook ops teams expect before adopting.

A tiny, thread-safe counter store plus a renderer that emits the Prometheus text
exposition format on `GET /metrics`. Live gauges (backends, swarm nodes, ledger
totals) are rendered on demand from the registry/swarm. Pure standard library — no
client library dependency.
"""

from __future__ import annotations

import threading


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[tuple, float] = {}
        self._lock = threading.Lock()

    def inc(self, name: str, labels: dict | None = None, n: float = 1.0) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + n

    @staticmethod
    def _fmt_labels(labels: tuple) -> str:
        if not labels:
            return ""
        inner = ",".join(f'{k}="{v}"' for k, v in labels)
        return "{" + inner + "}"

    def render(self, gauges: dict[str, float] | None = None) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        with self._lock:
            counters = dict(self._counters)
        for (name, labels), val in sorted(counters.items()):
            if name not in seen:
                lines.append(f"# TYPE {name} counter")
                seen.add(name)
            lines.append(f"{name}{self._fmt_labels(labels)} {val}")
        for name, val in sorted((gauges or {}).items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {val}")
        return "\n".join(lines) + "\n"
