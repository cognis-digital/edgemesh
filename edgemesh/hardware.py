"""Best-effort, cross-OS hardware detection — no third-party deps.

edgemesh uses this to "fit a model to the cluster": estimate how much GPU VRAM
and system RAM a node has, so it can recommend models that will actually run.

Everything degrades gracefully: if a probe fails we return None for that field
rather than raising, so this is safe to call on any machine (Linux, macOS,
Windows, headless servers, CI).
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class GPU:
    name: str
    vram_mb: int | None = None
    vendor: str = "unknown"  # nvidia | amd | apple | intel | unknown

    def to_dict(self) -> dict:
        return {"name": self.name, "vram_mb": self.vram_mb, "vendor": self.vendor}


@dataclass
class Hardware:
    os: str
    arch: str
    cpu_count: int | None = None
    ram_mb: int | None = None
    gpus: list[GPU] = field(default_factory=list)

    @property
    def total_vram_mb(self) -> int | None:
        vrams = [g.vram_mb for g in self.gpus if g.vram_mb]
        return sum(vrams) if vrams else None

    def to_dict(self) -> dict:
        return {
            "os": self.os, "arch": self.arch, "cpu_count": self.cpu_count,
            "ram_mb": self.ram_mb, "gpus": [g.to_dict() for g in self.gpus],
            "total_vram_mb": self.total_vram_mb,
        }


def _run(cmd: list[str], timeout: float = 6.0) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else None
    except Exception:
        return None


def _ram_mb() -> int | None:
    # POSIX: sysconf gives pages * page size
    try:
        if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
            return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024))
    except (ValueError, OSError):
        pass
    # Windows: GlobalMemoryStatusEx via ctypes
    if platform.system() == "Windows":
        try:
            import ctypes

            class _MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stat = _MEMSTAT()
            stat.dwLength = ctypes.sizeof(_MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys / (1024 * 1024))
        except Exception:
            pass
    return None


def _nvidia_gpus() -> list[GPU]:
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    gpus: list[GPU] = []
    if out:
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                gpus.append(GPU(name=parts[0], vram_mb=int(parts[1]), vendor="nvidia"))
    return gpus


def _amd_gpus() -> list[GPU]:
    # rocm-smi (Linux). VRAM in bytes under "VRAM Total Memory".
    out = _run(["rocm-smi", "--showmeminfo", "vram", "--csv"])
    gpus: list[GPU] = []
    if out:
        for line in out.strip().splitlines():
            m = re.search(r"(\d{6,})", line)  # bytes
            if m:
                gpus.append(GPU(name="AMD GPU", vram_mb=int(int(m.group(1)) / (1024 * 1024)), vendor="amd"))
    return gpus


def _apple_gpu() -> list[GPU]:
    # Apple Silicon: unified memory. Report total RAM as the VRAM ceiling.
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        ram = _ram_mb()
        return [GPU(name=f"Apple {platform.machine()} (unified)", vram_mb=ram, vendor="apple")]
    return []


def detect() -> Hardware:
    """Detect this machine's compute resources, best-effort."""
    hw = Hardware(os=platform.system() or "unknown", arch=platform.machine() or "unknown",
                  cpu_count=os.cpu_count(), ram_mb=_ram_mb())
    for probe in (_nvidia_gpus, _amd_gpus, _apple_gpu):
        gpus = probe()
        if gpus:
            hw.gpus.extend(gpus)
    return hw


def usable_vram_mb(hw: Hardware | None = None) -> int | None:
    """The VRAM budget edgemesh fits models into.

    Discrete GPU(s): total VRAM. Apple unified: ~70% of RAM (leave headroom for
    the OS). CPU-only: ~60% of RAM (models can run on CPU, just slowly).
    """
    hw = hw or detect()
    if hw.total_vram_mb and any(g.vendor in ("nvidia", "amd") for g in hw.gpus):
        return hw.total_vram_mb
    if any(g.vendor == "apple" for g in hw.gpus) and hw.ram_mb:
        return int(hw.ram_mb * 0.70)
    if hw.ram_mb:
        return int(hw.ram_mb * 0.60)
    return None
