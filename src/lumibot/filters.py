from __future__ import annotations

from dataclasses import dataclass

from lumibot.config import FiltersCfg
from lumibot.models import Source, TokenCandidate
from lumibot.util import as_float, dig, first_present


@dataclass
class FilterResult:
    ok: bool
    reason: str | None = None


def _mc_in_range(value: float | None, cfg: FiltersCfg) -> bool:
    if value is None:
        return False
    return cfg.mc_min <= value <= cfg.mc_max


@dataclass
class ExtensionResult:
    """mc_extension gate: hard reject and/or soft observability bump."""

    reject: bool = False
    soft: bool = False
    reason: str | None = None


def evaluate_mc_extension(cand: TokenCandidate, cfg: FiltersCfg) -> ExtensionResult:
    """Signal-only: market_cap / trigger_mc vs max_mc_extension."""
    if cand.source != Source.SIGNAL:
        return ExtensionResult()
    if cand.trigger_mc is None or cand.trigger_mc <= 0:
        return ExtensionResult()
    if cand.market_cap is None:
        return ExtensionResult()
    ratio = cand.market_cap / cand.trigger_mc
    if ratio <= cfg.max_mc_extension:
        return ExtensionResult()
    if cfg.enforce_mc_extension:
        return ExtensionResult(reject=True, reason="mc_extension")
    return ExtensionResult(soft=True, reason="mc_extension_soft")


def apply_light_filters(
    cand: TokenCandidate,
    cfg: FiltersCfg,
    *,
    platforms: list[str] | None = None,
) -> FilterResult:
    allow = [p.strip().lower() for p in (platforms or []) if p and p.strip()]
    if allow:
        plat = (cand.platform or "").strip().lower()
        if not plat:
            return FilterResult(False, "platform_missing")
        if plat not in allow:
            return FilterResult(False, "platform")

    if cand.market_cap is None:
        return FilterResult(False, "mc_missing")
    if not _mc_in_range(cand.market_cap, cfg):
        return FilterResult(False, "mc")
    if cand.source == Source.SIGNAL and cand.trigger_mc is not None:
        if not _mc_in_range(cand.trigger_mc, cfg):
            return FilterResult(False, "trigger_mc")
    if cand.liquidity is None:
        return FilterResult(False, "liq_missing")
    if cand.liquidity < cfg.liquidity_min:
        return FilterResult(False, "liq")
    if cand.top10_rate is None:
        return FilterResult(False, "top10_missing")
    if cand.top10_rate > cfg.top10_max:
        return FilterResult(False, "top10")
    if cand.holder_count is None:
        return FilterResult(False, "holders_missing")
    if cand.holder_count < cfg.holders_min:
        return FilterResult(False, "holders")
    if cand.visiting_count is None:
        return FilterResult(False, "visiting_missing")
    if cand.visiting_count < cfg.visiting_min:
        return FilterResult(False, "visiting")
    return FilterResult(True)


def extract_platform(raw: dict) -> str | None:
    v = first_present(raw, "platform", "launchpad", "exchange", "dex")
    if v is None:
        return None
    return str(v)


def extract_signal_fields(raw: dict) -> dict[str, float | None]:
    cur = raw.get("cur_data") if isinstance(raw.get("cur_data"), dict) else {}
    merged = {**raw, **cur}
    return {
        "market_cap": as_float(first_present(merged, "market_cap", "mc", "usd_market_cap")),
        "trigger_mc": as_float(first_present(merged, "trigger_mc", "trigger_market_cap")),
        "liquidity": as_float(first_present(merged, "liquidity", "liquidity_usd", "liq")),
        "top10_rate": as_float(first_present(merged, "top10_rate", "top_10_holder_rate", "top10")),
        "holder_count": as_float(first_present(merged, "holder_count", "holder", "holders")),
        "price": as_float(
            first_present(merged, "price")
            if not isinstance(merged.get("price"), dict)
            else dig(merged, "price", "price")
        ),
        "visiting_count": as_float(first_present(merged, "visiting_count")),
    }


def extract_trending_fields(raw: dict) -> dict[str, float | None]:
    return {
        "market_cap": as_float(first_present(raw, "market_cap", "mc", "usd_market_cap")),
        "trigger_mc": None,
        "liquidity": as_float(first_present(raw, "liquidity", "liquidity_usd", "liq")),
        "top10_rate": as_float(first_present(raw, "top10_rate", "top_10_holder_rate", "top10")),
        "holder_count": as_float(first_present(raw, "holder_count", "holder", "holders")),
        "price": as_float(
            first_present(raw, "price")
            if not isinstance(raw.get("price"), dict)
            else dig(raw, "price", "price")
        ),
        "visiting_count": as_float(first_present(raw, "visiting_count")),
    }


def merge_info_fields(cand: TokenCandidate, info: dict, *, force_visiting: bool = False) -> None:
    fields = extract_trending_fields(info)
    if cand.market_cap is None:
        cand.market_cap = fields["market_cap"]
    if cand.liquidity is None:
        cand.liquidity = fields["liquidity"]
    if cand.top10_rate is None:
        cand.top10_rate = fields["top10_rate"]
    if cand.holder_count is None:
        cand.holder_count = fields["holder_count"]
    if cand.price is None:
        cand.price = fields["price"]
    if force_visiting:
        # Signal visiting MUST come from token info; never keep payload fallback.
        cand.visiting_count = fields["visiting_count"]
    # Trending visiting MUST stay on payload only — never fill/overwrite from token info.
    if not cand.symbol:
        cand.symbol = info.get("symbol") or info.get("token_symbol")
    if not cand.name:
        cand.name = info.get("name") or info.get("token_name")
    if not cand.platform:
        cand.platform = extract_platform(info)
    if cand.open_timestamp is None:
        cand.open_timestamp = parse_open_timestamp(info)


def parse_open_timestamp(data: dict) -> float | None:
    ot = as_float(first_present(data, "open_timestamp", "open_time"))
    if ot is None:
        return None
    if ot > 1e12:
        ot = ot / 1000.0
    if ot <= 0:
        return None
    return ot
