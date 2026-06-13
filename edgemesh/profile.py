"""Node profiling — turn `hardware.detect()` into a swarm `HardwareProfile`.

This is the "Hardware Profiler" of a compute node: it classifies the accelerator
into one of the four supported families (Apple MLX / NVIDIA CUDA / AMD ROCm /
CPU-only) so the scheduler can place jobs that actually fit the device.
"""

from __future__ import annotations

import socket
import uuid

from edgemesh import hardware
from edgemesh.protocol import CLASS_C, HardwareProfile, NodeInfo

_VENDOR_TO_FAMILY = {"nvidia": "cuda", "amd": "rocm", "apple": "mlx"}


def node_profile() -> HardwareProfile:
    hw = hardware.detect()
    gpu = hw.gpus[0] if hw.gpus else None
    family = _VENDOR_TO_FAMILY.get(gpu.vendor, "cpu") if gpu else "cpu"
    return HardwareProfile(
        os=hw.os, arch=hw.arch, accelerator=family,
        cpu_cores=hw.cpu_count, ram_mb=hw.ram_mb,
        vram_mb=gpu.vram_mb if gpu else None,
        gpu_name=gpu.name if gpu else "",
    )


def build_node_info(name: str | None = None, node_class: str = CLASS_C,
                    endpoint: str = "", sharding: bool = False) -> NodeInfo:
    """Assemble this device's NodeInfo for swarm registration."""
    return NodeInfo(
        node_id=uuid.uuid4().hex[:12],
        name=name or socket.gethostname(),
        node_class=node_class,
        endpoint=endpoint,
        profile=node_profile(),
        sharding=sharding,
    )
