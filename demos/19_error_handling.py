"""Scenario 19 - clear errors: how edgemesh fails, on purpose.

Good infrastructure fails loudly and legibly. This demo walks the error paths -
routing an unserved model, scheduling a job that fits nowhere, overdrawing the
ledger, exceeding the relay hop cap, and building an empty circuit - and shows
each returns a clear, actionable signal instead of a mystery crash. Offline.
"""
from _common import rule

from edgemesh import limits
from edgemesh.backends import Backend
from edgemesh.executor import run_job
from edgemesh.ledger import Ledger
from edgemesh.protocol import CLASS_C, HardwareProfile, Job, NodeInfo
from edgemesh.registry import BackendRegistry
from edgemesh.router import NoBackendError, Router
from edgemesh.swarm import SwarmController


def _node(nid, vram, endpoint="http://x"):
    return NodeInfo(nid, nid, CLASS_C, endpoint,
                    HardwareProfile(os="L", arch="x", accelerator="cuda",
                                    ram_mb=32000, vram_mb=vram, gpu_name="G"))


def main() -> None:
    rule("ERROR HANDLING  -  fail loudly, legibly, and safely")

    print("\n[1] Routing a model nobody serves -> NoBackendError:")
    router = Router(BackendRegistry([Backend("a", "http://h:1", ["known"])]))
    try:
        router.resolve("gpt-4o")
    except NoBackendError as e:
        print(f"    {e}")

    print("\n[2] A job too big for any single node -> a sharding hint, not a crash:")
    sc = SwarmController()
    sc.register(_node("small", vram=4000))
    res = run_job(sc, Job.new("m", min_vram_mb=999999), {"messages": []}, "buyer")
    print(f"    ok={res['ok']}: {res['error']}")

    print("\n[3] Overdrawing the ledger -> a safe no-op, not a negative balance:")
    led = Ledger()
    led.grant("buyer", 1.0)
    ok = led.settle("buyer", "node", 100.0)
    print(f"    settle(100) with balance 1.0 -> {ok}; buyer still {led.balance('buyer')}")

    print(f"\n[4] Exceeding the {limits.MAX_CIRCUIT_HOPS}-hop relay cap -> rejected up front:")
    try:
        from edgemesh import relay
        if relay.HAVE_CRYPTO:
            circuit = [(f"http://r{i}", relay.gen_keypair()[1])
                       for i in range(limits.MAX_CIRCUIT_HOPS + 1)]
            try:
                relay.build_onion(circuit, "http://backend", {})
            except ValueError as e:
                print(f"    ValueError: {e}")
        else:
            print("    (cryptography not installed - relay fails closed; skipping)")
    except Exception as e:  # pragma: no cover - defensive
        print(f"    relay unavailable: {e}")

    print("\n[5] An empty relay circuit -> ValueError before any work is done:")
    try:
        from edgemesh import relay
        if relay.HAVE_CRYPTO:
            try:
                relay.build_onion([], "http://backend", {})
            except ValueError as e:
                print(f"    ValueError: {e}")
        else:
            print("    (cryptography not installed; skipping)")
    except Exception as e:  # pragma: no cover - defensive
        print(f"    relay unavailable: {e}")

    print("\nEvery failure here is a clear return value or a typed exception - never")
    print("a silent wrong answer or an unhandled stack trace in the hot path.")


if __name__ == "__main__":
    main()
