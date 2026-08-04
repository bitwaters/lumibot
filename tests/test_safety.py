from lumibot.config import SafetyThresholds
from lumibot.models import NormalizedSafety
from lumibot.safety import evaluate_safety, normalize_security


TH = SafetyThresholds()


def test_evm_tax_003_passes():
    s = NormalizedSafety(
        honeypot=False,
        renounced=True,
        open_source=True,
        buy_tax=0.03,
        sell_tax=0.03,
        rug_ratio=0.1,
        bundler_rate=0.1,
        rat_rate=0.1,
        wash_trading=False,
    )
    out = evaluate_safety("evm_v1", s, TH)
    assert not out.hard_fail


def test_evm_tax_006_rejects():
    s = NormalizedSafety(
        honeypot=False,
        renounced=True,
        open_source=True,
        buy_tax=0.06,
        sell_tax=0.03,
        wash_trading=False,
    )
    out = evaluate_safety("evm_v1", s, TH)
    assert out.hard_fail and out.reason == "safety_tax"


def test_empty_tax_is_zero():
    n = normalize_security({"buy_tax": "", "sell_tax": None, "is_honeypot": False, "is_renounced": True, "is_open_source": True})
    assert n.buy_tax == 0.0 and n.sell_tax == 0.0
    out = evaluate_safety("evm_v1", n, TH)
    assert not out.hard_fail


def test_sol_empty_honeypot_ignored():
    s = NormalizedSafety(
        honeypot=None,
        renounced_mint=True,
        renounced_freeze=True,
        wash_trading=False,
        rug_ratio=0.1,
        bundler_rate=0.1,
        rat_rate=0.1,
    )
    out = evaluate_safety("sol_v1", s, TH)
    assert not out.hard_fail


def test_bundler_field_priority():
    n = normalize_security({"bundler_rate": 0.1, "bundler_trader_amount_rate": 0.9})
    assert n.bundler_rate == 0.1
    n2 = normalize_security({"bundler_trader_amount_rate": 0.2})
    assert n2.bundler_rate == 0.2


def test_evm_missing_honeypot_rejects_when_strict():
    s = NormalizedSafety(
        honeypot=None,
        renounced=True,
        open_source=True,
        buy_tax=0.0,
        sell_tax=0.0,
        wash_trading=False,
        rug_ratio=0.1,
        bundler_rate=0.1,
        rat_rate=0.1,
    )
    out = evaluate_safety("evm_v1", s, SafetyThresholds(strict_missing=True))
    assert out.hard_fail and out.reason == "safety_honeypot_missing"


def test_evm_missing_renounced_rejects():
    s = NormalizedSafety(
        honeypot=False,
        renounced=None,
        open_source=True,
        buy_tax=0.0,
        sell_tax=0.0,
        wash_trading=False,
    )
    out = evaluate_safety("evm_v1", s, TH)
    assert out.hard_fail and out.reason in {"safety_renounced", "safety_renounced_missing"}
