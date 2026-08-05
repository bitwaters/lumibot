#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lumibot.config import load_app_config
from lumibot.gmgn.client import GmgnClient, RateLimiter


def _quote_tokens(chain_cfg: Any) -> list[str]:
    return [q.symbol for q in getattr(chain_cfg, "quote_tokens", [])]


def _extract_addr(row: dict[str, Any]) -> str | None:
    token_obj = row.get("token") if isinstance(row.get("token"), dict) else {}
    return (
        row.get("address")
        or row.get("token_address")
        or row.get("ca")
        or token_obj.get("address")
        or token_obj.get("token_address")
    )


async def sample_chain(chain: str, chain_cfg: Any, api_key: str) -> dict[str, Any]:
    limiter = RateLimiter(20, 6)
    client = GmgnClient(api_key, limiter, cache_ttl_sec=60, security_cache_ttl_sec=300)

    report: dict[str, Any] = {
        "chain": chain,
        "quote_tokens": _quote_tokens(chain_cfg),
        "sample_addr": None,
        "signal_count": 0,
        "trending_count": 0,
        "token_info_ok": False,
        "token_security_ok": False,
        "price_ok": False,
        "sample_token_info_fields": [],
        "errors": [],
    }

    try:
        signal_rows = await client.get_token_signal(chain, chain_cfg.sources.signal.types)
        report["signal_count"] = len(signal_rows)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"signal_fetch_failed: {exc}")
        signal_rows = []

    try:
        trending_rows: list[dict[str, Any]] = []
        trending_rows.extend(await client.get_trending(chain, chain_cfg.sources.trending.window))
        if chain_cfg.sources.trending_5m is not None and chain_cfg.sources.trending_5m.enabled:
            trending_rows.extend(await client.get_trending(chain, chain_cfg.sources.trending_5m.window))
        report["trending_count"] = len(trending_rows)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"trending_fetch_failed: {exc}")
        trending_rows = []

    sample_addr: str | None = None
    for row in signal_rows:
        sample_addr = _extract_addr(row)
        if sample_addr:
            break
    if not sample_addr:
        for row in trending_rows:
            sample_addr = _extract_addr(row)
            if sample_addr:
                break

    report["sample_addr"] = sample_addr

    if sample_addr:
        try:
            info = await client.get_token_info(chain, sample_addr, use_cache=False)
            report["token_info_ok"] = isinstance(info, dict) and bool(info)
            report["sample_token_info_fields"] = sorted((info or {}).keys()) if isinstance(info, dict) else []
            if report["token_info_ok"]:
                sec = await client.get_token_security(chain, sample_addr)
                report["token_security_ok"] = isinstance(sec, dict) and bool(sec)
                price, _mc = await client.get_price_and_market_cap(chain, sample_addr)
                report["price_ok"] = price is not None and price > 0
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"detail_fetch_failed: {exc}")

        if report["token_info_ok"] is False:
            report["errors"].append("token_info_missing_or_empty")
        if report["token_security_ok"] is False:
            report["errors"].append("security_info_missing_or_empty")
        if report["price_ok"] is False:
            report["errors"].append("price_missing_or_invalid")
    else:
        report["errors"].append("no_sample_addr")

    await client.aclose()
    return report


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample GMGN endpoints for a chain.")
    p.add_argument("--chain", required=True, choices=["sol", "bsc", "robinhood"])
    p.add_argument(
        "--config",
        default="config/chains.yaml",
        help="Path to lumibot config",
    )
    p.add_argument("--api-key", default=os.getenv("GMGN_API_KEY", ""), help="GMGN API key")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON report")
    p.add_argument("--require-ok", action="store_true", help="Exit non-zero if report does not meet checks")
    p.add_argument(
        "--min-signal",
        type=int,
        default=1,
        help="Minimum signal rows required (default 1)",
    )
    p.add_argument(
        "--min-trending",
        type=int,
        default=1,
        help="Minimum trending rows required (default 1)",
    )
    p.add_argument(
        "--require-quote-tokens",
        action="store_true",
        help="Require quote_tokens non-empty in config",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit("GMGN_API_KEY is required (or pass --api-key)")

    app = load_app_config(args.config)
    chain_cfg = app.chains.get(args.chain)
    if chain_cfg is None:
        raise SystemExit(f"chain missing in config: {args.chain}")

    try:
        report = await sample_chain(args.chain, chain_cfg, args.api_key)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"connectivity_check_failed: {exc}")

    report["config_path"] = str(Path(args.config).resolve())
    report["required_signal_min"] = args.min_signal
    report["required_trending_min"] = args.min_trending
    report["require_quote_tokens"] = args.require_quote_tokens
    report["signal_ok"] = report["signal_count"] >= args.min_signal
    report["trending_ok"] = report["trending_count"] >= args.min_trending
    report["quote_tokens_ok"] = (not args.require_quote_tokens) or bool(report["quote_tokens"])
    report["overall_ok"] = (
        report["signal_ok"]
        and report["trending_ok"]
        and report["token_info_ok"]
        and report["token_security_ok"]
        and report["price_ok"]
        and report["quote_tokens_ok"]
        and not report["errors"]
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"chain={report['chain']}")
        print(f"config={report['config_path']}")
        print(f"quote_tokens={','.join(report['quote_tokens']) or '(empty)'}")
        print(f"sample_addr={report['sample_addr']!r}")
        print(f"signal_count={report['signal_count']} (>= {args.min_signal}) -> {report['signal_ok']}")
        print(f"trending_count={report['trending_count']} (>= {args.min_trending}) -> {report['trending_ok']}")
        print(f"token_info_ok={report['token_info_ok']}")
        print(f"token_security_ok={report['token_security_ok']}")
        print(f"price_ok={report['price_ok']}")
        print(f"quote_tokens_ok={report['quote_tokens_ok']}")
        print(f"overall_ok={report['overall_ok']}")
        print(f"errors={report['errors']}")

    if args.require_ok and not report["overall_ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
