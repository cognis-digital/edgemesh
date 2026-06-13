"""Compute-credits + reputation ledger.

Nodes **earn credits** for completing jobs and consumers **spend credits** to run
them; completing/failing jobs moves a node's **reputation**, which the scheduler
uses to prefer reliable nodes.

IMPORTANT — this is an internal accounting unit, NOT a cryptocurrency or a
tradeable/investable security. edgemesh deliberately does not implement a
transferable on-chain token, an exchange, or any "buy/sell/stake for profit"
mechanism. Turning credits into a real token is a separate product + regulatory
(securities) decision and is intentionally out of scope here.

Persisted atomically to ~/.edgemesh/ledger.json.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_LEDGER = str(Path.home() / ".edgemesh" / "ledger.json")
START_REPUTATION = 1.0
MIN_REPUTATION = 0.1
MAX_REPUTATION = 5.0


class Ledger:
    def __init__(self, credits: dict[str, float] | None = None,
                 reputation: dict[str, float] | None = None) -> None:
        self.credits: dict[str, float] = dict(credits or {})
        self.reputation: dict[str, float] = dict(reputation or {})

    # --- credits -------------------------------------------------------------
    def balance(self, account: str) -> float:
        return round(self.credits.get(account, 0.0), 4)

    def grant(self, account: str, amount: float) -> float:
        """Seed/top up an account's credits (e.g. a consumer buying credits)."""
        self.credits[account] = self.balance(account) + max(0.0, amount)
        return self.balance(account)

    def settle(self, consumer: str, node: str, amount: float) -> bool:
        """Move `amount` credits consumer -> node for a completed job.

        Returns False (no-op) if the consumer can't cover it.
        """
        amount = max(0.0, amount)
        if self.balance(consumer) < amount:
            return False
        self.credits[consumer] = self.balance(consumer) - amount
        self.credits[node] = self.balance(node) + amount
        return True

    # --- reputation ----------------------------------------------------------
    def rep(self, node: str) -> float:
        return round(self.reputation.get(node, START_REPUTATION), 4)

    def record_outcome(self, node: str, success: bool) -> float:
        cur = self.rep(node)
        cur = cur * 1.05 if success else cur * 0.80   # reward success, penalize failure
        self.reputation[node] = max(MIN_REPUTATION, min(MAX_REPUTATION, cur))
        return self.rep(node)

    # --- persistence ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {"credits": self.credits, "reputation": self.reputation}

    @classmethod
    def load(cls, path: str = DEFAULT_LEDGER) -> "Ledger":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return cls(d.get("credits"), d.get("reputation"))

    def save(self, path: str = DEFAULT_LEDGER) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
