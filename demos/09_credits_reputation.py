"""Scenario 9 - the economics: how credits and reputation actually move.

edgemesh's ledger is an internal accounting unit (NOT a cryptocurrency): consumers
spend credits, nodes earn them, and completing/failing jobs moves a node's
reputation, which the scheduler uses to prefer reliable nodes. This demo walks a
funded consumer through several settlements and shows the books always balance and
reputation converges. Offline.
"""
from _common import rule

from edgemesh.ledger import MAX_REPUTATION, MIN_REPUTATION, Ledger


def main() -> None:
    rule("CREDITS + REPUTATION  -  the internal accounting unit (not a token)")

    led = Ledger()
    led.grant("acme-co", 20.0)
    print(f"\nSeed: acme-co granted 20 credits -> balance {led.balance('acme-co')}")

    print("\nSettling three jobs consumer -> node (2 credits each):")
    for i in range(3):
        ok = led.settle("acme-co", "node-x", 2.0)
        led.record_outcome("node-x", success=True)
        print(f"   job {i + 1}: settled={ok}  acme-co={led.balance('acme-co')}  "
              f"node-x={led.balance('node-x')}  rep={led.rep('node-x')}")

    print("\nOverdraw protection - a consumer can't spend credits it doesn't have:")
    print(f"   try to settle 999 with only {led.balance('acme-co')} left -> "
          f"{led.settle('acme-co', 'node-x', 999.0)} (no-op, books untouched)")

    print("\nReputation is bounded and converges (reward x1.05 / penalty x0.80):")
    flaky = Ledger()
    for _ in range(50):
        flaky.record_outcome("flaky", success=False)
    print(f"   50 failures -> reputation floors at {flaky.rep('flaky')} "
          f"(MIN={MIN_REPUTATION})")
    for _ in range(200):
        flaky.record_outcome("flaky", success=True)
    print(f"   then 200 successes -> caps at {flaky.rep('flaky')} (MAX={MAX_REPUTATION})")

    total = sum(led.credits.values())
    print(f"\nConservation: total credits in the system = {total} (nothing minted on transfer).")
    print("This is deliberately NOT a tradeable token - that's a separate product/regulatory call.")


if __name__ == "__main__":
    main()
