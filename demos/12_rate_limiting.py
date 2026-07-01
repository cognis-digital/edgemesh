"""Scenario 12 - abuse protection: the token-bucket rate limiter + hard caps.

A single caller shouldn't be able to exhaust the mesh. edgemesh applies a
thread-safe token-bucket limiter per caller and hard caps on body size, batch
size, and relay circuit length. This demo drives the limiter through a burst and
a refill (deterministic virtual clock) and prints the configured caps. Offline.
"""
from _common import rule

from edgemesh import limits
from edgemesh.limits import RateLimiter


def main() -> None:
    rule("RATE LIMITING + CAPS  -  one caller can't exhaust the network")

    rl = RateLimiter(rate_per_min=60, burst=5)  # 1 token/sec, bucket of 5
    print("\nToken bucket: burst=5, refill=1 token/sec. Hammering from one IP at t=0:")
    results = [rl.allow("1.2.3.4", now=0.0) for _ in range(8)]
    allowed = results.count(True)
    print(f"   8 back-to-back requests -> {allowed} allowed, {8 - allowed} throttled")

    print("\nAfter idling 3 seconds the bucket refills (3 tokens back):")
    refilled = [rl.allow("1.2.3.4", now=3.0) for _ in range(4)]
    print(f"   4 requests at t=3s -> {refilled.count(True)} allowed")

    print("\nLimiter is per-caller - a second IP has its own independent bucket:")
    other = [rl.allow("9.9.9.9", now=0.0) for _ in range(5)]
    print(f"   fresh IP: {other.count(True)}/5 allowed immediately")

    print("\nHard caps the gateway enforces:")
    print(f"   max request body   : {limits.MAX_BODY_BYTES // 1000} KB")
    print(f"   max map batch      : {limits.MAX_MAP_PROMPTS} prompts")
    print(f"   max relay circuit  : {limits.MAX_CIRCUIT_HOPS} hops")

    print("\nGraceful degradation: throttled callers get HTTP 429, not a crashed node.")


if __name__ == "__main__":
    main()
