"""A guided, first-run setup experience — the "rich UX" entry point.

`edgemesh setup` walks a new user through:
  1. detecting this machine's compute (CPU/RAM/GPU/VRAM),
  2. discovering inference backends already running locally,
  3. offering to register the Cognis fleet if it's up,
  4. recommending models that fit the detected hardware,
  5. saving a config so the gateway is ready to serve.

It is deliberately conversational and safe: every step asks before acting, and
nothing is destructive. Pure standard library (input/print).
"""

from __future__ import annotations

from edgemesh import catalog, hardware
from edgemesh.backends import Backend, probe
from edgemesh.registry import DEFAULT_CONFIG, BackendRegistry

COGNIS_FLEET = {
    "uncensored-fleet": "http://127.0.0.1:8774",
    "coding-fleet": "http://127.0.0.1:8772",
    "vision-fleet": "http://127.0.0.1:8773",
    "cognis-code": "http://127.0.0.1:11434",
}


def _ask(prompt: str, default: str = "y") -> bool:
    try:
        ans = input(f"{prompt} [{'Y/n' if default == 'y' else 'y/N'}] ").strip().lower()
    except EOFError:
        return default == "y"
    if not ans:
        return default == "y"
    return ans.startswith("y")


def run(config_path: str = DEFAULT_CONFIG, *, _input=input) -> int:
    print("\n=== edgemesh setup ===\n")

    # 1. hardware
    hw = hardware.detect()
    vram = hardware.usable_vram_mb(hw)
    print(f"This machine: {hw.os}/{hw.arch}, {hw.cpu_count} CPU(s), "
          f"{(hw.ram_mb or 0) // 1024} GB RAM")
    if hw.gpus:
        for g in hw.gpus:
            print(f"  GPU: {g.name} ({g.vendor}, "
                  f"{(g.vram_mb or 0) // 1024} GB VRAM)" if g.vram_mb else f"  GPU: {g.name}")
    else:
        print("  GPU: none detected (CPU inference)")
    print(f"  -> usable model budget: ~{(vram or 0) // 1024} GB\n")

    registry = BackendRegistry.load(config_path)

    # 2. discover local backends
    if _ask("Scan localhost for running inference backends?"):
        added = registry.discover_local()
        print(f"  discovered: {', '.join(added) if added else '(none running)'}\n")

    # 3. Cognis fleet
    up = [n for n, url in COGNIS_FLEET.items() if probe(url, timeout=2.0) is not None]
    if up and _ask(f"Register the Cognis fleet found up ({', '.join(up)})?"):
        for name in up:
            models = probe(COGNIS_FLEET[name]) or []
            registry.add(Backend(name=name, base_url=COGNIS_FLEET[name], models=models))
        print("  registered Cognis fleet\n")

    # 4. recommend models that fit
    fits = catalog.fit(vram, include_uncensored=True)[:6]
    print("Models that should fit this machine (largest first):")
    for c in fits:
        flag = " [uncensored]" if c.uncensored else ""
        print(f"  - {c.id:22s} ~{c.approx_vram_mb // 1024} GB  {c.modality}{flag}  ({c.pull})")
    print("  Pull any of these later with: edgemesh pull <id>\n")

    # 5. save
    registry.save(config_path)
    print(f"Saved config to {config_path}")
    print(f"Registered backends: {', '.join(registry.names()) or '(none yet)'}")
    print("\nNext:  edgemesh serve      (run the gateway)")
    print("       edgemesh menu       (interactive menu)\n")
    return 0
