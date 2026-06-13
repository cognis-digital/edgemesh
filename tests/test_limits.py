"""Minimum-hardware admission + token-bucket rate limiting."""

from __future__ import annotations

from edgemesh import limits
from edgemesh.protocol import HardwareProfile


def _p(accel, ram=None, vram=None):
    return HardwareProfile(os="Linux", arch="x86_64", accelerator=accel, ram_mb=ram, vram_mb=vram)


def test_floor_admission():
    assert limits.meets_floor(_p("cpu", ram=4096))
    assert not limits.meets_floor(_p("cpu", ram=1024))   # below 2 GB floor


def test_inference_capability():
    assert limits.is_inference_capable(_p("cuda", ram=16000, vram=8000))
    assert not limits.is_inference_capable(_p("cuda", ram=16000, vram=2000))  # tiny VRAM
    assert limits.is_inference_capable(_p("mlx", ram=16000))                  # unified mem
    assert limits.is_inference_capable(_p("cpu", ram=8192))                   # CPU floor
    assert not limits.is_inference_capable(_p("cpu", ram=4096))               # too little RAM


def test_rate_limiter_burst_then_block_then_refill():
    rl = limits.RateLimiter(rate_per_min=60, burst=2)  # 1 token/sec, burst 2
    assert rl.allow("ip", now=0.0)
    assert rl.allow("ip", now=0.0)
    assert not rl.allow("ip", now=0.0)        # burst exhausted
    assert rl.allow("ip", now=1.0)            # ~1 token refilled after 1s
    # a different caller has its own bucket
    assert rl.allow("other", now=0.0)
