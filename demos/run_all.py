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
    "06_router_failover",
    "07_distributed_execution",
    "08_scatter_gather",
    "09_credits_reputation",
    "10_sharding_presets",
    "11_auth_audit",
    "12_rate_limiting",
    "13_streaming_metered",
    "14_cluster_join",
    "15_relay_directory",
    "16_privacy_gate",
    "17_metrics_observability",
    "18_vscode_integration",
    "19_error_handling",
    "20_end_to_end",
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
