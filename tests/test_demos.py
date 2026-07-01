"""Tests for the demo scenarios and their bundled offline fixtures.

These run each demo's `main()` (exercising the same code paths the demos narrate)
and assert the fixtures and helper invariants hold, so the demos double as smoke
tests under pytest.
"""
import importlib
import os
import sys

import pytest

DEMOS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demos")
sys.path.insert(0, DEMOS_DIR)

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


@pytest.mark.parametrize("name", SCENARIOS)
def test_demo_runs_clean(name, capsys):
    mod = importlib.import_module(name)
    mod.main()                       # must not raise
    out = capsys.readouterr().out
    assert out.strip()               # produced narrated output


def test_run_all_imports_every_scenario():
    run_all = importlib.import_module("run_all")
    assert run_all.SCENARIOS == SCENARIOS


def test_fixture_registry_catalog_has_failover():
    from _common import fixture_registry
    catalog = fixture_registry().model_catalog()
    # llama3.1-8b is served by three backends -> a real failover set
    assert len(catalog["llama3.1-8b"]) == 3


def test_fixture_nodes_cover_all_trust_classes():
    from _common import fixture_nodes
    classes = {n.node_class for n in fixture_nodes()}
    assert classes == {"A", "B", "C"}
    assert any(n.sharding for n in fixture_nodes())


def test_stub_backend_round_trips():
    import json
    import urllib.request
    from _common import stub_backend
    with stub_backend(["m1", "m2"]) as base:
        with urllib.request.urlopen(base + "/v1/models", timeout=5) as r:
            data = json.loads(r.read())
        ids = sorted(m["id"] for m in data["data"])
        assert ids == ["m1", "m2"]


def test_swarm_privacy_gate_excludes_untrusted_nodes():
    from _common import fixture_nodes
    from edgemesh.protocol import DATA_CONFIDENTIAL, Job
    from edgemesh.scheduler import eligible
    job = Job.new("x", data_class=DATA_CONFIDENTIAL, min_vram_mb=1000)
    elig = eligible(job, fixture_nodes())
    assert [n.node_class for n in elig] == ["A"]
