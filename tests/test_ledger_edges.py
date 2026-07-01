"""Edge cases and error paths for the credits + reputation ledger:
overdraw protection, negative amounts, reputation bounds, rounding, persistence."""

from __future__ import annotations

import json

from edgemesh.ledger import (MAX_REPUTATION, MIN_REPUTATION, START_REPUTATION,
                             Ledger)


# --- credits -----------------------------------------------------------------
def test_balance_unknown_account_is_zero():
    assert Ledger().balance("nobody") == 0.0


def test_grant_accumulates():
    led = Ledger()
    led.grant("a", 5)
    led.grant("a", 3)
    assert led.balance("a") == 8.0


def test_grant_negative_is_noop():
    led = Ledger()
    led.grant("a", 10)
    led.grant("a", -4)  # clamped to 0
    assert led.balance("a") == 10.0


def test_settle_moves_credits():
    led = Ledger()
    led.grant("c", 10)
    assert led.settle("c", "n", 4) is True
    assert led.balance("c") == 6.0 and led.balance("n") == 4.0


def test_settle_blocks_overdraw():
    led = Ledger()
    led.grant("c", 3)
    assert led.settle("c", "n", 4) is False
    assert led.balance("c") == 3.0 and led.balance("n") == 0.0


def test_settle_exact_balance_ok():
    led = Ledger()
    led.grant("c", 5)
    assert led.settle("c", "n", 5) is True
    assert led.balance("c") == 0.0 and led.balance("n") == 5.0


def test_settle_negative_amount_is_zero_transfer():
    led = Ledger()
    led.grant("c", 5)
    assert led.settle("c", "n", -3) is True  # clamped to 0, always affordable
    assert led.balance("c") == 5.0 and led.balance("n") == 0.0


def test_settle_zero_amount_ok():
    led = Ledger()
    assert led.settle("c", "n", 0) is True


def test_balance_is_rounded_to_4dp():
    led = Ledger()
    led.grant("a", 1.0 / 3.0)
    assert led.balance("a") == round(1.0 / 3.0, 4)


# --- reputation --------------------------------------------------------------
def test_rep_default_is_start():
    assert Ledger().rep("new") == START_REPUTATION


def test_rep_success_increases():
    led = Ledger()
    before = led.rep("n")
    after = led.record_outcome("n", True)
    assert after > before


def test_rep_failure_decreases():
    led = Ledger()
    before = led.rep("n")
    after = led.record_outcome("n", False)
    assert after < before


def test_rep_floor():
    led = Ledger()
    for _ in range(100):
        led.record_outcome("n", False)
    assert led.rep("n") >= MIN_REPUTATION


def test_rep_ceiling():
    led = Ledger()
    for _ in range(500):
        led.record_outcome("n", True)
    assert led.rep("n") <= MAX_REPUTATION


def test_rep_independent_per_node():
    led = Ledger()
    led.record_outcome("a", True)
    led.record_outcome("b", False)
    assert led.rep("a") > START_REPUTATION > led.rep("b")


# --- persistence -------------------------------------------------------------
def test_to_dict_shape():
    led = Ledger({"a": 5.0}, {"a": 2.0})
    d = led.to_dict()
    assert d == {"credits": {"a": 5.0}, "reputation": {"a": 2.0}}


def test_save_load_roundtrip(tmp_path):
    path = str(tmp_path / "ledger.json")
    led = Ledger()
    led.grant("acme", 42)
    led.record_outcome("node", True)
    led.save(path)
    reloaded = Ledger.load(path)
    assert reloaded.balance("acme") == 42.0
    assert reloaded.rep("node") == led.rep("node")


def test_load_missing_file_is_empty(tmp_path):
    led = Ledger.load(str(tmp_path / "absent.json"))
    assert led.credits == {} and led.reputation == {}


def test_save_is_atomic_valid_json(tmp_path):
    path = str(tmp_path / "l.json")
    Ledger({"x": 1.0}, {}).save(path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["credits"]["x"] == 1.0


def test_save_creates_parent_dir(tmp_path):
    path = str(tmp_path / "nested" / "deep" / "l.json")
    Ledger({"y": 2.0}, {}).save(path)
    assert Ledger.load(path).balance("y") == 2.0


def test_constructor_copies_inputs():
    credits = {"a": 1.0}
    led = Ledger(credits, None)
    led.grant("a", 1.0)
    assert credits["a"] == 1.0  # original not mutated
