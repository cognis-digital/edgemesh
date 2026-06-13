"""Sharding-backend presets."""

from __future__ import annotations

from edgemesh import presets


def test_presets_are_well_formed():
    assert {"exo", "vllm-ray", "petals", "llamacpp-rpc"} <= set(presets.keys())
    for key in presets.keys():
        p = presets.get(key)
        assert p.key == key
        assert p.default_url.startswith("http") and p.default_url.rstrip("/").endswith(("/v1", "/v1-openai"))
        assert p.start_hint and p.docs_url.startswith("http")


def test_multi_machine_flagged_honestly():
    # exo / vLLM+Ray genuinely span machines; TGI / NIM are single-node multi-GPU
    assert presets.get("exo").multi_machine is True
    assert presets.get("vllm-ray").multi_machine is True
    assert presets.get("tgi").multi_machine is False
    assert presets.get("nim").multi_machine is False


def test_get_unknown_is_none():
    assert presets.get("nope") is None
