"""Scenario 1 - platform engineers: one catalog, one endpoint, across everything.

You have models running in more than one place - the Cognis fleet, an Ollama
server, maybe a friend's GPU box - and nothing unifies them. edgemesh registers
each OpenAI-compatible backend, merges their model lists into one catalog, and
routes a requested model to a backend that actually serves it. This demo does
that against the bundled offline backend snapshot (no servers needed).
"""
from _common import fixture_registry, rule

from edgemesh.router import NoBackendError, Router


def main() -> None:
    rule("UNIFY BACKENDS  -  one model catalog, one /v1 endpoint")

    reg = fixture_registry()
    print("\nRegistered backends (in the field, `edgemesh discover` finds these):")
    for b in reg.backends():
        print(f"   {b.name:<18} {b.base_url:<24} {len(b.models)} model(s)")

    catalog = reg.model_catalog()
    print(f"\nAggregated catalog: {len(catalog)} distinct model(s) across the mesh.")
    print("A model served by more than one backend is automatically a failover set:")
    for model, owners in sorted(catalog.items()):
        tag = "  <- served by several backends" if len(owners) > 1 else ""
        print(f"   {model:<24} -> {', '.join(owners)}{tag}")

    router = Router(reg)
    print("\nRouting requests through the gateway:")
    for want in ["mistral-7b", "llama3.1-8b", "coding-fleet::qwen2.5-coder-7b"]:
        backend, upstream = router.resolve(want)
        note = "  (explicit backend::model pin)" if "::" in want else ""
        print(f"   ask '{want}'  ->  {backend.name}  (upstream id '{upstream}'){note}")

    # candidates() is the failover order the gateway tries in turn
    fall = router.candidates("llama3.1-8b")
    print(f"\nFailover order for 'llama3.1-8b': {[b.name for b in fall]}")

    try:
        router.resolve("gpt-4o")
    except NoBackendError as e:
        print(f"\nAsking for a model nobody serves fails cleanly: {e}")

    print("\nOne client, one base URL - the mesh decides who actually answers.")


if __name__ == "__main__":
    main()
