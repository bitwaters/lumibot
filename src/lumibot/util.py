from __future__ import annotations

from typing import Any

CHAIN_TAGS: dict[str, str] = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}


def chain_tag(chain: str) -> str:
    return CHAIN_TAGS.get(chain, chain.upper())


def mc_from_price_ratio(
    mark_mc: float | None, mark_price: float | None, ref_price: float | None
) -> float | None:
    """Scale a market cap quote to a different reference price (same supply)."""
    if mark_mc is None or mark_price is None or ref_price is None:
        return None
    if mark_price <= 0 or ref_price <= 0:
        return None
    return mark_mc * (ref_price / mark_price)


def as_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def as_bool(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y"}:
        return True
    if s in {"0", "false", "no", "n"}:
        return False
    return None


def first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None and data[key] != "":
            return data[key]
    return None


def dig(data: dict[str, Any], *path: str) -> Any:
    cur: Any = data
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur
