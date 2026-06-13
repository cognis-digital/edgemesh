"""Pure helpers behind the guided setup wizard."""

from __future__ import annotations

from edgemesh.protocol import HardwareProfile
from edgemesh.wizard import hardware_verdict, next_steps


def _p(accel, ram=None, vram=None):
    return HardwareProfile(os="Linux", arch="x86_64", accelerator=accel, ram_mb=ram, vram_mb=vram)


def test_hardware_verdict_tiers():
    assert hardware_verdict(_p("cpu", ram=1024))["tier"] == "below-floor"
    assert hardware_verdict(_p("cpu", ram=4096))["tier"] == "relay-only"
    assert hardware_verdict(_p("cuda", ram=16000, vram=8000))["tier"] == "inference"
    v = hardware_verdict(_p("cuda", ram=16000, vram=8000))
    assert v["meets_floor"] and v["inference_capable"]


def test_next_steps_are_role_tailored():
    allsteps = next_steps("all", tls=True, relay=True)
    assert any("serve --tls --relay-key" in s for s in allsteps)
    assert any("edgemesh node http://" in s for s in next_steps("node"))
    assert any("gen-relay-key" in s for s in next_steps("relay"))
    assert all("edgemesh menu" in s for s in [next_steps("all")[-1]])  # menu always last
