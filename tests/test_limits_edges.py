"""Minimum-hardware admission policy + rate-limiter (token bucket) edge cases."""

from __future__ import annotations

from edgemesh import limits
from edgemesh.limits import (MAX_BODY_BYTES, MAX_CIRCUIT_HOPS, MAX_MAP_PROMPTS,
                             MIN_INFERENCE_RAM_MB, MIN_RAM_MB, RateLimiter,
                             is_inference_capable, meets_floor)
from edgemesh.protocol import HardwareProfile


def _profile(accel="cpu", ram=None, vram=None):
    return HardwareProfile(os="L", arch="x", accelerator=accel, ram_mb=ram, vram_mb=vram)


# --- admission floor ---------------------------------------------------------
def test_meets_floor_true_at_min():
    assert meets_floor(_profile(ram=MIN_RAM_MB))


def test_meets_floor_false_below_min():
    assert not meets_floor(_profile(ram=MIN_RAM_MB - 1))


def test_meets_floor_none_ram_is_false():
    assert not meets_floor(_profile(ram=None))


# --- inference capability ----------------------------------------------------
def test_inference_gpu_needs_min_vram():
    assert is_inference_capable(_profile("cuda", vram=limits.MIN_GPU_VRAM_MB))
    assert not is_inference_capable(_profile("cuda", vram=limits.MIN_GPU_VRAM_MB - 1))


def test_inference_rocm_gpu_gate():
    assert is_inference_capable(_profile("rocm", vram=8000))
    assert not is_inference_capable(_profile("rocm", vram=100))


def test_inference_cpu_gates_on_ram():
    assert is_inference_capable(_profile("cpu", ram=MIN_INFERENCE_RAM_MB))
    assert not is_inference_capable(_profile("cpu", ram=MIN_INFERENCE_RAM_MB - 1))


def test_inference_apple_unified_gates_on_ram():
    assert is_inference_capable(_profile("mlx", ram=16000))
    assert not is_inference_capable(_profile("mlx", ram=1000))


def test_inference_gpu_without_vram_is_false():
    assert not is_inference_capable(_profile("cuda", vram=None))


# --- caps are sane -----------------------------------------------------------
def test_caps_are_positive():
    assert MAX_BODY_BYTES > 0 and MAX_MAP_PROMPTS > 0 and MAX_CIRCUIT_HOPS > 0


# --- rate limiter ------------------------------------------------------------
def test_rate_limiter_allows_within_burst():
    rl = RateLimiter(rate_per_min=60, burst=5)
    assert all(rl.allow("ip", now=0.0) for _ in range(5))


def test_rate_limiter_blocks_over_burst():
    rl = RateLimiter(rate_per_min=60, burst=3)
    for _ in range(3):
        rl.allow("ip", now=0.0)
    assert rl.allow("ip", now=0.0) is False  # bucket empty


def test_rate_limiter_refills_over_time():
    rl = RateLimiter(rate_per_min=60, burst=1)  # 1 token/sec
    assert rl.allow("ip", now=0.0) is True
    assert rl.allow("ip", now=0.0) is False
    assert rl.allow("ip", now=1.0) is True  # refilled after 1s


def test_rate_limiter_is_per_key():
    rl = RateLimiter(rate_per_min=60, burst=1)
    assert rl.allow("a", now=0.0) is True
    assert rl.allow("b", now=0.0) is True  # different caller, own bucket


def test_rate_limiter_burst_is_ceiling():
    rl = RateLimiter(rate_per_min=6000, burst=2)  # fast refill
    rl.allow("ip", now=0.0)
    # even after a long idle, tokens cap at burst
    allowed = sum(rl.allow("ip", now=1000.0) for _ in range(10))
    assert allowed == 2  # never more than burst back-to-back
