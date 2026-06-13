"""Minimum-hardware policy + abuse protections for the swarm.

Two jobs:
  1. **Admission** — define the minimum hardware a node needs to be useful, and
     whether it can actually serve inference (vs. only relay / participate).
  2. **Rate limiting + caps** — a thread-safe token-bucket limiter plus hard caps
     on request size, scatter-gather batch size, and relay circuit length, so a
     single caller can't exhaust or abuse the network.

Pure standard library.
"""

from __future__ import annotations

import threading
import time

# --- minimum hardware policy -------------------------------------------------
MIN_RAM_MB = 2048            # floor to join at all (relay / scheduler participant)
MIN_INFERENCE_RAM_MB = 8192  # floor to be handed CPU inference (small models)
MIN_GPU_VRAM_MB = 4096       # floor for a discrete GPU to be inference-useful

# --- abuse caps --------------------------------------------------------------
MAX_BODY_BYTES = 1_000_000   # reject oversized request bodies (1 MB)
MAX_MAP_PROMPTS = 64         # cap a single scatter-gather batch
MAX_CIRCUIT_HOPS = 6         # cap relay circuit length (DoS / loop guard)


def meets_floor(profile) -> bool:
    """Can this device join the swarm at all?"""
    return (profile.ram_mb or 0) >= MIN_RAM_MB


def is_inference_capable(profile) -> bool:
    """Should the scheduler hand this device actual inference jobs?"""
    if profile.accelerator in ("cuda", "rocm"):
        return (profile.vram_mb or 0) >= MIN_GPU_VRAM_MB
    # apple unified memory and cpu both gate on RAM
    return (profile.ram_mb or 0) >= MIN_INFERENCE_RAM_MB


class RateLimiter:
    """Token-bucket limiter keyed by caller (IP / consumer id). Thread-safe."""

    def __init__(self, rate_per_min: float = 60.0, burst: int = 30) -> None:
        self.rate = rate_per_min / 60.0     # tokens per second
        self.burst = float(burst)
        self._state: dict[str, list[float]] = {}  # key -> [tokens, last_ts]
        self._lock = threading.Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        with self._lock:
            tokens, last = self._state.get(key, [self.burst, now])
            tokens = min(self.burst, tokens + (now - last) * self.rate)  # refill
            if tokens < 1.0:
                self._state[key] = [tokens, now]
                return False
            self._state[key] = [tokens - 1.0, now]
            return True
