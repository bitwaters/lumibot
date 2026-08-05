from __future__ import annotations

import time
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


def evaluate_chase(cand: TokenCandidate, current_price: float | None, cfg: FiltersCfg) -> bool:
    """Signal-only: reject when the market already ran past the push price.

    current_price is the fresh quote fetched at execution time; cand.push_price is
    the price from the push payload. A large positive gap means the signal arrived
    late and we would be buying the top of a pump.
    """
    if cfg.chase_max_pct <= 0:
        return False
    if cand.source != Source.SIGNAL:
        return False
    if cand.push_price is None or cand.push_price <= 0:
        return False
    if current_price is None or current_price <= 0:
        return False
    return current_price > cand.push_price * (1.0 + cfg.chase_max_pct)


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
    visiting_min = cfg.visiting_min
    if cand.source == Source.TRENDING and cfg.visiting_min_trending is not None:
        # Both sources now gate on token-info visiting; this stays as a per-source
        # threshold knob, not a payload-lag allowance.
        visiting_min = cfg.visiting_min_trending
    if cand.visiting_count is None:
        return FilterResult(False, "visiting_missing")
    if cand.visiting_count < visiting_min:
        return FilterResult(False, "visiting")

    # --- Age filter (requires open_timestamp from token_info) ---
    if cand.open_timestamp is not None:
        age_sec = time.time() - cand.open_timestamp
        if cfg.age_min_sec > 0 and age_sec < cfg.age_min_sec:
            return FilterResult(False, "too_new")
        if cfg.age_max_sec > 0 and age_sec > cfg.age_max_sec:
            return FilterResult(False, "too_old")

    # --- Liquidity/MC ratio filter ---
    if cfg.liquidity_ratio_min > 0 and cand.market_cap is not None and cand.market_cap > 0:
        liq_ratio = (cand.liquidity or 0.0) / cand.market_cap
        if liq_ratio < cfg.liquidity_ratio_min:
            return FilterResult(False, "liq_ratio")

    # --- Volume filters ---
    if cfg.volume_1h_min > 0:
        if cand.volume_1h is None:
            return FilterResult(False, "volume_missing")
        if cand.volume_1h < cfg.volume_1h_min:
            return FilterResult(False, "volume_1h")
    if cfg.volume_mc_ratio_min > 0 and cand.market_cap is not None and cand.market_cap > 0:
        vol_ratio = (cand.volume_1h or 0.0) / cand.market_cap
        if vol_ratio < cfg.volume_mc_ratio_min:
            return FilterResult(False, "volume_mc_ratio")

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
        "volume_1h": as_float(first_present(merged, "volume_1h", "volume", "vol_1h")),
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
        "volume_1h": as_float(first_present(raw, "volume_1h", "volume", "vol_1h")),
    }


def flatten_token_info(info: dict) -> dict:
    """Lift nested GMGN token_info fields (stat/pool) into a flat dict for extractors."""
    flat = dict(info)
    stat = info.get("stat")
    if isinstance(stat, dict):
        for key in (
            "holder_count",
            "top_10_holder_rate",
            "visiting_count",
        ):
            if key in stat and flat.get(key) is None:
                flat[key] = stat[key]
    pool = info.get("pool")
    if isinstance(pool, dict) and flat.get("liquidity") is None and pool.get("liquidity") is not None:
        flat["liquidity"] = pool.get("liquidity")
    return flat


def merge_info_fields(cand: TokenCandidate, info: dict, *, force_visiting: bool = False) -> None:
    fields = extract_trending_fields(flatten_token_info(info))
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
    if cand.volume_1h is None:
        cand.volume_1h = fields["volume_1h"]
    if force_visiting:
        # Visiting MUST come from token info for both signal and trending gates;
        # never keep payload fallback (payload vs token_info visiting differ wildly).
        cand.visiting_count = fields["visiting_count"]
    # Trending visiting MUST stay on payload only during gate — never fill/overwrite from token info.
    if not cand.symbol:
        cand.symbol = info.get("symbol") or info.get("token_symbol")
    if not cand.name:
        cand.name = info.get("name") or info.get("token_name")
    if not cand.platform:
        cand.platform = extract_platform(info)
    if cand.open_timestamp is None:
        cand.open_timestamp = parse_open_timestamp(info)


def apply_push_snapshot(
    cand: TokenCandidate,
    info: dict,
    *,
    price: float | None,
    market_cap: float | None,
) -> None:
    """Overwrite card/open fields from a post-gate uncached token_info snapshot."""
    fields = extract_trending_fields(flatten_token_info(info))
    cand.liquidity = fields["liquidity"]
    cand.top10_rate = fields["top10_rate"]
    cand.holder_count = fields["holder_count"]
    cand.visiting_count = fields["visiting_count"]
    ot = parse_open_timestamp(info)
    if ot is not None:
        cand.open_timestamp = ot
    sym = info.get("symbol") or info.get("token_symbol")
    if sym:
        cand.symbol = sym
    name = info.get("name") or info.get("token_name")
    if name:
        cand.name = name
    cand.price = price if price is not None and price > 0 else fields["price"]
    # Prefer parser MC from the same snapshot; never keep gate-era MC on the push card.
    cand.market_cap = market_cap if market_cap is not None and market_cap > 0 else None


def parse_open_timestamp(data: dict) -> float | None:
    ot = as_float(first_present(data, "open_timestamp", "open_time"))
    if ot is None:
        return None
    if ot > 1e12:
        ot = ot / 1000.0
    if ot <= 0:
        return None
    return ot
