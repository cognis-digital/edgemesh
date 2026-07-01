"""Edge cases for hardware detection + fit: graceful degradation, VRAM budgets,
GPU dataclass behavior, and the HardwareProfile.usable_vram_mb policy."""

from __future__ import annotations

from edgemesh import hardware
from edgemesh.hardware import GPU, Hardware, detect, usable_vram_mb
from edgemesh.protocol import HardwareProfile


# --- GPU / Hardware dataclasses ----------------------------------------------
def test_gpu_to_dict():
    g = GPU(name="RTX 4090", vram_mb=24000, vendor="nvidia")
    assert g.to_dict() == {"name": "RTX 4090", "vram_mb": 24000, "vendor": "nvidia"}


def test_hardware_total_vram_sums_gpus():
    hw = Hardware(os="Linux", arch="x86_64",
                  gpus=[GPU("a", 8000, "nvidia"), GPU("b", 16000, "nvidia")])
    assert hw.total_vram_mb == 24000


def test_hardware_total_vram_none_when_no_gpus():
    assert Hardware(os="Linux", arch="x86_64").total_vram_mb is None


def test_hardware_total_vram_ignores_none_entries():
    hw = Hardware(os="Linux", arch="x86_64",
                  gpus=[GPU("a", None, "nvidia"), GPU("b", 8000, "nvidia")])
    assert hw.total_vram_mb == 8000


def test_hardware_to_dict_shape():
    hw = Hardware(os="Linux", arch="x86_64", cpu_count=8, ram_mb=16000,
                  gpus=[GPU("g", 8000, "nvidia")])
    d = hw.to_dict()
    assert d["os"] == "Linux" and d["total_vram_mb"] == 8000
    assert d["gpus"][0]["name"] == "g"


# --- detect() degrades gracefully -------------------------------------------
def test_detect_never_raises():
    hw = detect()
    assert isinstance(hw, Hardware)
    assert hw.os and hw.arch  # always populated (fallback 'unknown')


def test_detect_reports_cpu_count():
    assert detect().cpu_count is None or detect().cpu_count >= 1


# --- usable_vram_mb budget policy -------------------------------------------
def test_usable_vram_discrete_gpu_is_total_vram():
    hw = Hardware(os="Linux", arch="x86_64", ram_mb=64000,
                  gpus=[GPU("rtx", 24000, "nvidia")])
    assert usable_vram_mb(hw) == 24000


def test_usable_vram_apple_is_70pct_ram():
    hw = Hardware(os="Darwin", arch="arm64", ram_mb=64000,
                  gpus=[GPU("apple", 64000, "apple")])
    assert usable_vram_mb(hw) == int(64000 * 0.70)


def test_usable_vram_cpu_only_is_60pct_ram():
    hw = Hardware(os="Linux", arch="x86_64", ram_mb=32000)
    assert usable_vram_mb(hw) == int(32000 * 0.60)


def test_usable_vram_none_when_nothing_known():
    hw = Hardware(os="Linux", arch="x86_64")
    assert usable_vram_mb(hw) is None


def test_usable_vram_prefers_discrete_over_ram():
    # a box with both a discrete GPU and lots of RAM should report GPU VRAM
    hw = Hardware(os="Linux", arch="x86_64", ram_mb=256000,
                  gpus=[GPU("rtx", 8000, "nvidia")])
    assert usable_vram_mb(hw) == 8000


def test_usable_vram_intel_gpu_falls_back_to_ram():
    # unknown/intel vendor GPUs aren't counted as discrete VRAM -> RAM policy
    hw = Hardware(os="Linux", arch="x86_64", ram_mb=16000,
                  gpus=[GPU("intel", 2000, "intel")])
    assert usable_vram_mb(hw) == int(16000 * 0.60)


# --- HardwareProfile.usable_vram_mb (the swarm-side profile) -----------------
def test_profile_cuda_uses_vram():
    p = HardwareProfile(os="L", arch="x", accelerator="cuda", vram_mb=12000, ram_mb=64000)
    assert p.usable_vram_mb() == 12000


def test_profile_rocm_uses_vram():
    p = HardwareProfile(os="L", arch="x", accelerator="rocm", vram_mb=16000, ram_mb=64000)
    assert p.usable_vram_mb() == 16000


def test_profile_mlx_uses_70pct_ram():
    p = HardwareProfile(os="Darwin", arch="arm64", accelerator="mlx", ram_mb=64000)
    assert p.usable_vram_mb() == int(64000 * 0.70)


def test_profile_cpu_uses_60pct_ram():
    p = HardwareProfile(os="L", arch="x", accelerator="cpu", ram_mb=16000)
    assert p.usable_vram_mb() == int(16000 * 0.60)


def test_profile_none_when_no_memory_info():
    p = HardwareProfile(os="L", arch="x", accelerator="cpu")
    assert p.usable_vram_mb() is None


def test_profile_cuda_without_vram_falls_back_to_ram():
    p = HardwareProfile(os="L", arch="x", accelerator="cuda", vram_mb=None, ram_mb=8000)
    assert p.usable_vram_mb() == int(8000 * 0.60)


# --- internal probes are safe ------------------------------------------------
def test_ram_probe_returns_int_or_none():
    val = hardware._ram_mb()
    assert val is None or isinstance(val, int)


def test_run_missing_binary_returns_none():
    assert hardware._run(["definitely-not-a-real-binary-xyz", "--x"]) is None
