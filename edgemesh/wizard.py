"""A comprehensive, guided, multi-step setup for edgemesh.

`edgemesh setup` walks a new operator through every decision needed to stand up a
node — role, a hardware check against the minimum-hardware policy, backend
discovery, model fit + download, mutual TLS, the privacy relay, sharding for
oversized models, and the active abuse limits — then saves a config and prints
tailored next-step commands.

The decision logic lives in small pure helpers (testable); `run()` just drives
them and asks before doing anything. Pure standard library.
"""

from __future__ import annotations

from edgemesh import catalog, hardware, limits, presets
from edgemesh.backends import Backend, probe
from edgemesh.registry import DEFAULT_CONFIG, BackendRegistry

COGNIS_FLEET = {
    "uncensored-fleet": "http://127.0.0.1:8774",
    "coding-fleet": "http://127.0.0.1:8772",
    "vision-fleet": "http://127.0.0.1:8773",
    "cognis-code": "http://127.0.0.1:11434",
}

ROLES = {
    "1": ("all", "All-in-one (coordinator + compute node)"),
    "2": ("coordinator", "Coordinator only (gateway + scheduler)"),
    "3": ("node", "Compute node (join an existing coordinator)"),
    "4": ("relay", "Privacy relay (forward onion traffic; no inference)"),
}


# --- pure helpers (unit-tested) ----------------------------------------------
def hardware_verdict(profile) -> dict:
    """Classify a device against the minimum-hardware policy."""
    floor = limits.meets_floor(profile)
    infer = limits.is_inference_capable(profile)
    if not floor:
        tier = "below-floor"
        note = f"under the {limits.MIN_RAM_MB} MB RAM floor — can't join."
    elif infer:
        tier = "inference"
        note = "can serve inference jobs."
    else:
        tier = "relay-only"
        note = "can relay / coordinate, but is under-spec for inference jobs."
    return {"meets_floor": floor, "inference_capable": infer, "tier": tier, "note": note}


def next_steps(role: str, *, tls: bool = False, relay: bool = False) -> list[str]:
    """Tailored commands to run after setup, given the chosen role/options."""
    steps: list[str] = []
    if role in ("all", "coordinator"):
        serve = "edgemesh serve"
        if tls:
            serve += " --tls"
        if relay:
            serve += " --relay-key ~/.edgemesh/relay.key"
        steps.append(serve + "        # start the gateway / control plane")
    if role == "node":
        steps.append("edgemesh node http://<coordinator-ip>:8780 --class C   # join the swarm")
    if role == "relay":
        steps.append("edgemesh gen-relay-key && edgemesh serve --relay-key ~/.edgemesh/relay.key")
    steps.append("edgemesh menu          # interactive control surface")
    return steps


def _ask(prompt: str, default: str = "y") -> bool:
    try:
        ans = input(f"{prompt} [{'Y/n' if default == 'y' else 'y/N'}] ").strip().lower()
    except EOFError:
        return default == "y"
    return default == "y" if not ans else ans.startswith("y")


# --- the guided flow ---------------------------------------------------------
def run(config_path: str = DEFAULT_CONFIG, *, _input=input) -> int:  # pragma: no cover
    print("\n=== edgemesh setup ===\n")

    # Step 1 — role
    print("What is this machine's role?")
    for k, (_, label) in ROLES.items():
        print(f"  {k}. {label}")
    role = ROLES.get(_input("role [1]: ").strip() or "1", ROLES["1"])[0]

    # Step 2 — hardware check vs minimum policy
    hw = hardware.detect()
    v = hardware_verdict(hardware_profile := _profile(hw))
    print(f"\nHardware: {hw.os}/{hw.arch}, {hw.cpu_count} CPU, {(hw.ram_mb or 0)//1024} GB RAM, "
          f"GPU: {', '.join(g.name for g in hw.gpus) or 'none'} ({hardware_profile.accelerator})")
    print(f"  Verdict: {v['tier']} — {v['note']}")
    if not v["meets_floor"]:
        print("  This device is below the join floor; you can still run a coordinator from it.")

    registry = BackendRegistry.load(config_path)

    # Step 3 — backends (compute roles)
    if role in ("all", "node") and _ask("\nScan localhost for inference backends?"):
        added = registry.discover_local()
        print(f"  discovered: {', '.join(added) if added else '(none running)'}")
        up = [n for n, u in COGNIS_FLEET.items() if probe(u, timeout=2.0) is not None]
        if up and _ask(f"Register the Cognis fleet found up ({', '.join(up)})?"):
            for name in up:
                registry.add(Backend(name=name, base_url=COGNIS_FLEET[name], models=probe(COGNIS_FLEET[name]) or []))

    # Step 4 — model fit + download
    if role in ("all", "node") and v["inference_capable"]:
        vram = hardware.usable_vram_mb(hw)
        fits = catalog.fit(vram, include_uncensored=True)[:6]
        print(f"\nModels that fit (~{(vram or 0)//1024} GB budget):")
        for c in fits:
            print(f"  - {c.id:22s} ~{c.approx_vram_mb//1024} GB  {c.modality}"
                  + ("  [uncensored]" if c.uncensored else ""))
        if fits and _ask(f"Pull the top pick ({fits[0].id}) now?", "n"):
            from edgemesh import manager
            print("  " + manager.pull(fits[0])[1])

    # Step 5 — sharding for oversized models
    if role in ("all", "node") and not v["inference_capable"]:
        print("\nFor models too big for this device, register a sharding backend:")
        for key in ("exo", "vllm-ray"):
            print(f"  edgemesh node <coordinator> --preset {key}   # {presets.get(key).title}")

    # Step 6 — security (mTLS)
    use_tls = False
    if role in ("all", "coordinator") and _ask("\nEnable mutual TLS (require client certs)?", "n"):
        use_tls = True
        print("  run:  edgemesh gen-certs   (then serve --tls)")

    # Step 7 — privacy relay
    use_relay = False
    if _ask("\nRun a privacy relay on this node?", "n"):
        use_relay = True
        print("  run:  edgemesh gen-relay-key   (needs: pip install edgemesh[relay])")

    # Step 8 — abuse limits summary
    print(f"\nActive abuse limits: rate-limited per IP; body <= {limits.MAX_BODY_BYTES//1000} KB; "
          f"map <= {limits.MAX_MAP_PROMPTS} prompts; relay <= {limits.MAX_CIRCUIT_HOPS} hops.")

    # Step 9 — save + tailored next steps
    registry.save(config_path)
    print(f"\nSaved config to {config_path}. Next:")
    for s in next_steps(role, tls=use_tls, relay=use_relay):
        print("  " + s)
    return 0


def _profile(hw):
    """Map detected hardware to a swarm HardwareProfile (for the verdict)."""
    from edgemesh.profile import node_profile
    return node_profile()
