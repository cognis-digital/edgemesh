"""The numbered interactive menu — one place to drive the whole cluster.

`edgemesh menu` opens a classic numbered console menu wiring every capability:
discovery, backends, the Cognis fleet, hardware fit, the model catalog +
download, the cluster, the gateway, and the setup wizard. Pure stdlib.
"""

from __future__ import annotations

from edgemesh import __version__, catalog, hardware, manager, wizard
from edgemesh.backends import Backend, probe
from edgemesh.gateway import serve
from edgemesh.registry import DEFAULT_CONFIG, BackendRegistry

MENU = """
========================  edgemesh {ver}  ========================
  Discover & connect
    1) Scan localhost for backends            6) Show model catalog (this cluster)
    2) Register the Cognis fleet              7) List registered backends
    3) Add a backend by URL
  Models & hardware                          Cluster & serve
    4) Detect hardware (fit budget)           8) Run the gateway (serve /v1)
    5) Browse model catalog + download        9) Cluster: show nodes / how to join
  Setup
   10) Guided setup wizard                    0) Quit
==================================================================
"""


def _print_catalog(vram):
    print(f"\nModels fitting ~{(vram or 0)//1024} GB (largest first; [u]=uncensored):")
    for i, c in enumerate(catalog.fit(vram), 1):
        u = "[u]" if c.uncensored else "   "
        print(f"  {i:2d}. {u} {c.id:24s} ~{c.approx_vram_mb//1024:>2} GB  {c.modality:9s} {c.pull}")
    return catalog.fit(vram)


def run(config_path: str = DEFAULT_CONFIG, *, _input=input) -> int:
    registry = BackendRegistry.load(config_path)
    while True:
        print(MENU.format(ver=__version__))
        try:
            choice = _input("select> ").strip()
        except EOFError:
            return 0

        if choice == "0":
            print("bye")
            return 0
        elif choice == "1":
            added = registry.discover_local()
            registry.save(config_path)
            print(f"  discovered: {', '.join(added) if added else '(none)'}")
        elif choice == "2":
            n = 0
            for name, url in wizard.COGNIS_FLEET.items():
                models = probe(url, timeout=2.0)
                if models is not None:
                    registry.add(Backend(name=name, base_url=url, models=models)); n += 1
            registry.save(config_path)
            print(f"  registered {n} Cognis backend(s)")
        elif choice == "3":
            name = _input("  name: ").strip()
            url = _input("  base_url (e.g. http://10.0.0.5:8000): ").strip()
            registry.add(Backend(name=name, base_url=url, models=probe(url) or []))
            registry.save(config_path)
            print(f"  added {name}")
        elif choice == "4":
            hw = hardware.detect()
            print(f"  {hw.os}/{hw.arch}, {hw.cpu_count} CPU, {(hw.ram_mb or 0)//1024} GB RAM, "
                  f"GPUs: {', '.join(g.name for g in hw.gpus) or 'none'}")
            print(f"  usable model budget: ~{(hardware.usable_vram_mb(hw) or 0)//1024} GB")
        elif choice == "5":
            vram = hardware.usable_vram_mb()
            fits = _print_catalog(vram)
            sel = _input("  pull which # (blank=skip): ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(fits):
                ok, msg = manager.pull(fits[int(sel) - 1])
                print("  " + msg)
        elif choice == "6":
            cat = registry.model_catalog()
            if not cat:
                print("  (no models — discover or add a backend first)")
            for model in sorted(cat):
                print(f"  {model}\t{', '.join(cat[model])}")
        elif choice == "7":
            for b in registry.backends():
                print(f"  {b.name}\t{b.base_url}\t{len(b.models)} model(s)")
            if not registry.names():
                print("  (none)")
        elif choice == "8":
            port = (_input("  port [8780]: ").strip() or "8780")
            print(f"  starting gateway on :{port} (Ctrl-C to stop)")
            serve(registry, port=int(port))
        elif choice == "9":
            print("  On any other device (same network), run:")
            print("    edgemesh join http://<this-host-ip>:8780")
            print("  Its local backends will join this cluster's /v1 catalog.")
        elif choice == "10":
            wizard.run(config_path)
            registry = BackendRegistry.load(config_path)
        else:
            print("  ?")
