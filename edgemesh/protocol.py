"""Shared wire types + security primitives for NexusCompute.

This is the contract between a **node** (installed on a user device) and the
**control plane** (orchestration). Pure standard library, JSON-serializable, and
transport-agnostic — see `transport.py` for how messages move.

Security here is deliberately minimal but real: HMAC-signed, short-lived bearer
tokens (no plaintext secrets on the wire). mTLS / signed-profile attestation are
roadmap (see ROADMAP.md); the seam is here so they can slot in.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass, field

PROTOCOL_VERSION = "0.1"

# Node trust tiers (diagram: Class A/B/C).
CLASS_A = "A"  # trusted infrastructure (datacenters, enterprise, confidential compute)
CLASS_B = "B"  # private swarm (approved contributors, encrypted jobs)
CLASS_C = "C"  # public network (community compute, non-sensitive)
NODE_CLASSES = (CLASS_A, CLASS_B, CLASS_C)

# Data sensitivity -> minimum node class allowed to handle it (privacy engine).
DATA_PUBLIC = "public"
DATA_PRIVATE = "private"
DATA_CONFIDENTIAL = "confidential"


@dataclass
class HardwareProfile:
    os: str
    arch: str
    accelerator: str          # mlx | cuda | rocm | cpu
    cpu_cores: int | None = None
    ram_mb: int | None = None
    vram_mb: int | None = None
    gpu_name: str = ""
    # best-effort telemetry (None when unknown)
    bandwidth_mbps: float | None = None
    latency_ms: float | None = None
    thermal_state: str | None = None
    battery_pct: int | None = None

    def usable_vram_mb(self) -> int | None:
        if self.vram_mb and self.accelerator in ("cuda", "rocm"):
            return self.vram_mb
        if self.accelerator == "mlx" and self.ram_mb:
            return int(self.ram_mb * 0.70)        # unified memory
        if self.ram_mb:
            return int(self.ram_mb * 0.60)        # cpu fallback
        return None


@dataclass
class NodeInfo:
    node_id: str
    name: str
    node_class: str
    endpoint: str                       # how the control plane / peers reach it
    profile: HardwareProfile
    reputation: float = 1.0
    last_seen: float = 0.0
    # A sharding node fronts a runtime that splits one model across machines
    # (exo / Petals / vLLM+Ray / llama.cpp RPC). It can serve models too big for a
    # single device, so the scheduler exempts it from the per-node VRAM filter.
    sharding: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "NodeInfo":
        prof = d.get("profile") or {}
        return cls(node_id=d["node_id"], name=d.get("name", ""),
                   node_class=d.get("node_class", CLASS_C), endpoint=d.get("endpoint", ""),
                   profile=HardwareProfile(**prof) if not isinstance(prof, HardwareProfile) else prof,
                   reputation=float(d.get("reputation", 1.0)), last_seen=float(d.get("last_seen", 0.0)),
                   sharding=bool(d.get("sharding", False)))


@dataclass
class Job:
    job_id: str
    model: str
    data_class: str = DATA_PUBLIC
    min_vram_mb: int = 0
    modality: str = "text"
    max_price: float = 0.0              # credits the consumer will pay
    submitted_by: str = ""

    @staticmethod
    def new(model: str, **kw) -> "Job":
        return Job(job_id=uuid.uuid4().hex[:12], model=model, **kw)


@dataclass
class Assignment:
    job_id: str
    node_id: str
    price: float
    shards: list[str] = field(default_factory=list)


# --- security: HMAC short-lived bearer tokens ---------------------------------
def issue_token(secret: str, node_id: str, ttl_s: int = 300) -> str:
    """A signed, short-lived token: base64(node_id|expiry|hmac)."""
    expiry = int(time.time()) + ttl_s
    msg = f"{node_id}|{expiry}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{node_id}|{expiry}|{sig}".encode()).decode()


def verify_token(secret: str, token: str) -> str | None:
    """Return the node_id if the token is valid and unexpired, else None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        node_id, expiry, sig = raw.split("|")
    except Exception:
        return None
    if int(expiry) < int(time.time()):
        return None
    expect = hmac.new(secret.encode(), f"{node_id}|{expiry}".encode(), hashlib.sha256).hexdigest()
    return node_id if hmac.compare_digest(sig, expect) else None


def dumps(obj) -> bytes:
    return json.dumps(obj, default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o)).encode()
