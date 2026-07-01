"""Edge cases for the Router: explicit backend syntax, candidate/failover lists,
ambiguous models, and error paths."""

from __future__ import annotations

import pytest

from edgemesh.backends import Backend
from edgemesh.registry import BackendRegistry
from edgemesh.router import EXPLICIT_SEP, NoBackendError, Router


def _reg(*backends):
    return BackendRegistry(list(backends))


def test_resolve_single_backend():
    r = Router(_reg(Backend("a", "http://h:1", ["m"])))
    backend, upstream = r.resolve("m")
    assert backend.name == "a" and upstream == "m"


def test_resolve_first_backend_alphabetically_when_ambiguous():
    r = Router(_reg(Backend("zeta", "http://h:1", ["m"]), Backend("alpha", "http://h:2", ["m"])))
    backend, _ = r.resolve("m")
    assert backend.name == "alpha"  # model_catalog sorts owners, first wins


def test_resolve_explicit_backend_wins():
    r = Router(_reg(Backend("a", "http://h:1", ["m"]), Backend("b", "http://h:2", ["m"])))
    backend, upstream = r.resolve("b::m")
    assert backend.name == "b" and upstream == "m"


def test_resolve_explicit_forwards_bare_model_id():
    r = Router(_reg(Backend("fleet", "http://h:1", ["llama3"])))
    _, upstream = r.resolve("fleet::llama3")
    assert upstream == "llama3"


def test_resolve_explicit_unknown_backend_raises():
    r = Router(_reg(Backend("a", "http://h:1", ["m"])))
    with pytest.raises(NoBackendError):
        r.resolve("ghost::m")


def test_resolve_unknown_model_raises():
    r = Router(_reg(Backend("a", "http://h:1", ["m"])))
    with pytest.raises(NoBackendError):
        r.resolve("nope")


def test_resolve_empty_registry_raises():
    with pytest.raises(NoBackendError):
        Router(_reg()).resolve("anything")


def test_resolve_explicit_does_not_require_backend_to_list_model():
    # explicit routing forwards whatever bare id follows the separator
    r = Router(_reg(Backend("a", "http://h:1", ["listed"])))
    backend, upstream = r.resolve("a::unlisted")
    assert backend.name == "a" and upstream == "unlisted"


def test_candidates_returns_all_owners_for_failover():
    r = Router(_reg(Backend("a", "http://h:1", ["m"]), Backend("b", "http://h:2", ["m"])))
    names = {b.name for b in r.candidates("m")}
    assert names == {"a", "b"}


def test_candidates_empty_for_unknown_model():
    r = Router(_reg(Backend("a", "http://h:1", ["m"])))
    assert r.candidates("unknown") == []


def test_candidates_explicit_single_backend():
    r = Router(_reg(Backend("a", "http://h:1", ["m"]), Backend("b", "http://h:2", ["m"])))
    cands = r.candidates("a::m")
    assert len(cands) == 1 and cands[0].name == "a"


def test_candidates_explicit_unknown_backend_empty():
    r = Router(_reg(Backend("a", "http://h:1", ["m"])))
    assert r.candidates("ghost::m") == []


def test_explicit_sep_constant():
    assert EXPLICIT_SEP == "::"


def test_resolve_model_with_colon_but_not_double():
    # a single colon is part of the model id (e.g. ollama tags), not explicit syntax
    r = Router(_reg(Backend("a", "http://h:1", ["llama3.1:8b"])))
    backend, upstream = r.resolve("llama3.1:8b")
    assert backend.name == "a" and upstream == "llama3.1:8b"
