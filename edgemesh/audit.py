"""Append-only audit logging — the compliance/forensics record buyers ask for.

Every privileged action (job submit, inference, node register, relay forward) can be
written as one JSON line: when, which principal, from where, what model/job, and the
outcome. Append-only JSONL is simple, tamper-evident-friendly (ship it to a WORM store
/ SIEM), and dependency-free. Off by default; enable with `edgemesh serve --audit`.

Prompt/response *content* is never logged — only metadata — so the audit trail itself
doesn't become a data-exfiltration surface.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

DEFAULT_AUDIT = str(Path.home() / ".edgemesh" / "audit.log")


class AuditLog:
    def __init__(self, path: str = DEFAULT_AUDIT) -> None:
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def record(self, action: str, *, principal: str = "anonymous", client: str = "",
               model: str = "", outcome: str = "", extra: dict | None = None) -> dict:
        event = {"ts": round(time.time(), 3), "action": action, "principal": principal,
                 "client": client, "model": model, "outcome": outcome}
        if extra:
            event.update(extra)
        line = json.dumps(event, sort_keys=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return event

    def tail(self, n: int = 50) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out
