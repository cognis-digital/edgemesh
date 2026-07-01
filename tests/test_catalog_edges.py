"""Edge cases for the model catalog + fit-to-hardware selection."""

from __future__ import annotations

from edgemesh import catalog
from edgemesh.catalog import CATALOG, ModelCard, by_id, fit, modalities


def test_catalog_nonempty_and_unique_ids():
    ids = [c.id for c in CATALOG]
    assert len(ids) == len(set(ids))  # no duplicate handles


def test_modelcard_to_dict_roundtrip_fields():
    c = CATALOG[0]
    d = c.to_dict()
    assert set(d) == {"id", "family", "params_b", "modality", "approx_vram_mb",
                      "pull", "uncensored", "note"}


def test_by_id_found():
    assert by_id("llama3.1-8b") is not None


def test_by_id_missing_returns_none():
    assert by_id("no-such-model") is None


def test_modalities_sorted_unique():
    mods = modalities()
    assert mods == sorted(set(mods))
    assert "text" in mods


# --- fit ---------------------------------------------------------------------
def test_fit_none_budget_returns_all():
    assert len(fit(None)) == len(CATALOG)


def test_fit_sorted_largest_first():
    cards = fit(50000)
    vrams = [c.approx_vram_mb for c in cards]
    assert vrams == sorted(vrams, reverse=True)


def test_fit_respects_headroom():
    # budget = int(vram*headroom). At 1000 MB * 0.9 = 900 -> only <=900 fit
    cards = fit(1000, headroom=0.9)
    assert all(c.approx_vram_mb <= 900 for c in cards)
    assert any(c.approx_vram_mb == 900 for c in cards)  # boundary inclusive


def test_fit_tiny_budget_returns_nothing():
    assert fit(100) == []


def test_fit_modality_filter():
    cards = fit(None, modality="code")
    assert cards and all(c.modality == "code" for c in cards)


def test_fit_modality_filter_vision():
    cards = fit(None, modality="vision")
    assert all(c.modality == "vision" for c in cards)


def test_fit_exclude_uncensored():
    cards = fit(None, include_uncensored=False)
    assert all(not c.uncensored for c in cards)
    # sanity: the full catalog does contain uncensored models
    assert any(c.uncensored for c in CATALOG)


def test_fit_include_uncensored_default():
    assert any(c.uncensored for c in fit(None))


def test_fit_big_budget_includes_large_models():
    cards = fit(48000)
    assert any(c.approx_vram_mb >= 40000 for c in cards)


def test_fit_negative_budget_returns_nothing():
    assert fit(-5000) == []


def test_fit_headroom_one_uses_full_budget():
    cards = fit(6500, headroom=1.0)
    assert any(c.approx_vram_mb == 6500 for c in cards)


def test_catalog_has_all_size_tiers():
    vrams = [c.approx_vram_mb for c in CATALOG]
    assert min(vrams) < 2000        # tiny/edge exists
    assert max(vrams) > 25000       # large exists


def test_modelcard_is_frozen():
    import dataclasses
    c = CATALOG[0]
    try:
        c.id = "mutated"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ModelCard should be frozen")
