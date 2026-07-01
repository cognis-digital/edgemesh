"""Scenario 13 - streaming + metered billing: pay for tokens actually produced.

Streaming jobs settle on the tokens that actually flow, not a flat price. The
StreamMeter counts completion tokens as an OpenAI SSE stream passes (preferring an
explicit usage field, else counting content deltas), and metered_stream bills
consumer -> node on completion - even if the client disconnects mid-stream. This
demo feeds a synthetic SSE stream through both, with no network. Offline.
"""
from _common import rule

from edgemesh.executor import StreamMeter, metered_stream
from edgemesh.protocol import CLASS_C, HardwareProfile, NodeInfo
from edgemesh.swarm import SwarmController

import json


def _sse(obj):
    return b"data: " + json.dumps(obj).encode() + b"\n"


class _FakeStream:
    """Stands in for a live urllib streaming response."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, size):
        return self._chunks.pop(0) if self._chunks else b""

    def close(self):
        pass


def main() -> None:
    rule("STREAMING + METERED BILLING  -  charge for tokens actually produced")

    print("\nCounting tokens as an SSE stream flows (content deltas):")
    meter = StreamMeter()
    for tok in ["Hello", " there", " world"]:
        meter.feed(_sse({"choices": [{"delta": {"content": tok}}]}))
    print(f"   3 content deltas -> metered {meter.tokens} tokens")

    print("\nAn explicit usage field wins over the delta estimate when present:")
    m2 = StreamMeter()
    m2.feed(_sse({"choices": [{"delta": {"content": "x"}}]}))
    m2.feed(_sse({"choices": [{"delta": {}}], "usage": {"completion_tokens": 42}}))
    print(f"   backend reported usage.completion_tokens=42 -> metered {m2.tokens}")

    print("\nEnd-to-end metered settlement (price 0.5 credits/token):")
    sc = SwarmController()
    sc.ledger.grant("acme-co", 100.0)
    sc.register(NodeInfo("node-x", "node-x", CLASS_C, "http://node-x",
                         HardwareProfile(os="L", arch="x", accelerator="cuda",
                                         ram_mb=32000, vram_mb=12000, gpu_name="G")))
    stream = _FakeStream([_sse({"choices": [{"delta": {"content": c}}]}) for c in "abcd"])
    relayed = list(metered_stream(stream, sc, "node-x", "acme-co", price_per_token=0.5))
    print(f"   streamed {len(relayed)} chunks; 4 tokens x 0.5 = "
          f"{sc.ledger.balance('node-x')} credits to node-x")
    print(f"   acme-co balance now {sc.ledger.balance('acme-co')}; node reputation "
          f"{sc.ledger.rep('node-x')} (clean finish rewarded)")

    print("\nBilling runs in a finally-block, so a client disconnect still pays for output.")


if __name__ == "__main__":
    main()
