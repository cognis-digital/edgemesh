"""Run every demo scenario end to end.

    python demos/run_all.py

Each scenario is independent and uses bundled offline fixtures (no models, no
network), so they can be run in any order or on their own. Exits non-zero if any
scenario raises.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCENARIOS = [
    "01_unify_backends",
    "02_fit_models_to_hardware",
    "03_swarm_scheduling",
    "04_privacy_relay",
    "05_live_gateway",
]


def main() -> None:
    for name in SCENARIOS:
        mod = importlib.import_module(name)
        mod.main()
    print("\n" + "=" * 72)
    print("  All demo scenarios completed.")
    print("=" * 72)


if __name__ == "__main__":
    main()
