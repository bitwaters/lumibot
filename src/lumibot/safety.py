from __future__ import annotations

from lumibot.config import SafetyThresholds
from lumibot.models import NormalizedSafety
from lumibot.util import as_bool, as_float, first_present


def normalize_security(raw: dict) -> NormalizedSafety:
    bundler = as_float(first_present(raw, "bundler_rate", "bundler_trader_amount_rate"))
    return NormalizedSafety(
        honeypot=as_bool(first_present(raw, "is_honeypot", "honeypot")),
        renounced=as_bool(first_present(raw, "is_renounced", "owner_renounced", "renounced")),
        open_source=as_bool(first_present(raw, "is_open_source", "open_source")),
        renounced_mint=as_bool(first_present(raw, "renounced_mint")),
        renounced_freeze=as_bool(
            first_present(raw, "renounced_freeze_account", "renounced_freeze")
        ),
        buy_tax=_tax(raw.get("buy_tax")),
        sell_tax=_tax(raw.get("sell_tax")),
        rug_ratio=as_float(raw.get("rug_ratio")),
        bundler_rate=bundler,
        rat_rate=as_float(raw.get("rat_trader_amount_rate")),
        wash_trading=as_bool(first_present(raw, "is_wash_trading")),
        creator_hold=as_bool(first_present(raw, "creator_hold", "creator_token_status")),
    )


def _tax(v) -> float | None:
    if v is None or v == "":
        return 0.0
    return as_float(v)


def evaluate_safety(
    profile: str,
    safety: NormalizedSafety,
    thresholds: SafetyThresholds,
) -> NormalizedSafety:
    out = safety
    out.hard_fail = False
    out.reason = None
    out.warnings = list(safety.warnings)

    if out.wash_trading is True:
        return _fail(out, "safety_wash")

    if out.rug_ratio is not None and out.rug_ratio > thresholds.rug_max:
        return _fail(out, "safety_rug")
    if out.bundler_rate is not None and out.bundler_rate > thresholds.bundler_max:
        return _fail(out, "safety_bundler")
    if out.rat_rate is not None and out.rat_rate > thresholds.rat_max:
        return _fail(out, "safety_rat")

    if profile == "sol_v1":
        return _sol_v1(out)
    if profile == "evm_v1":
        return _evm_v1(out, thresholds)
    return _fail(out, "safety_unknown_profile")


def _sol_v1(out: NormalizedSafety) -> NormalizedSafety:
    # honeypot empty ignored; true still hard fail if present
    if out.honeypot is True:
        return _fail(out, "safety_honeypot")
    if out.renounced_mint is not True:
        return _fail(out, "safety_mint")
    if out.renounced_freeze is not True:
        return _fail(out, "safety_freeze")
    if out.creator_hold is True:
        out.warnings.append("creator_hold")
    return out


def _evm_v1(out: NormalizedSafety, thresholds: SafetyThresholds) -> NormalizedSafety:
    if out.honeypot is None:
        return _fail(out, "safety_honeypot_missing")
    if out.honeypot is True:
        return _fail(out, "safety_honeypot")
    if out.renounced is None:
        return _fail(out, "safety_renounced_missing")
    if out.renounced is not True:
        return _fail(out, "safety_renounced")
    if out.open_source is None:
        return _fail(out, "safety_open_source_missing")
    if out.open_source is not True:
        return _fail(out, "safety_open_source")
    buy = 0.0 if out.buy_tax is None else out.buy_tax
    sell = 0.0 if out.sell_tax is None else out.sell_tax
    if buy > thresholds.tax_max or sell > thresholds.tax_max:
        return _fail(out, "safety_tax")
    if out.creator_hold is True:
        out.warnings.append("creator_hold")
    return out


def _fail(out: NormalizedSafety, reason: str) -> NormalizedSafety:
    out.hard_fail = True
    out.reason = reason
    return out
