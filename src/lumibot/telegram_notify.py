from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from lumibot.config import AppConfig
from lumibot.exec_types import ExecResult, PaperTradeEvent
from lumibot.models import Source, TokenCandidate
from lumibot.util import chain_tag as _chain_tag
from lumibot.util import mc_from_price_ratio

logger = logging.getLogger(__name__)

GMGN_URL = {
    "sol": "https://gmgn.ai/sol/token/{addr}",
    "bsc": "https://gmgn.ai/bsc/token/{addr}",
    "robinhood": "https://gmgn.ai/rh/token/{addr}",
}

WARN_LABELS = {
    "creator_hold": "开发者持仓",
}

CLOSE_REASON_LABELS = {
    "hard_stop": "硬止损",
    "trail": "峰值回撤",
    "pre_stage1_trail": "回本前回撤",
    "timeout": "超时平仓",
    "stage1_full": "回本全平",
    "stage1": "回本减仓",
    "close": "平仓",
}

CLOSE_ICONS = {
    "hard_stop": "📉",
    "trail": "📉",
    "pre_stage1_trail": "📉",
    "timeout": "⌛",
    "stage1_full": "📉",
    "stage1": "✂️",
    "close": "📉",
}

SOURCE_LABELS = {
    "signal": "信号",
    "trending": "热门",
}

REASON_LABELS = {
    "mc": "市值",
    "mc_missing": "市值缺失",
    "trigger_mc": "触发市值",
    "liq": "流动性",
    "liq_missing": "流动性缺失",
    "liq_ratio": "流动性占比",
    "top10": "Top10",
    "top10_missing": "Top10缺失",
    "holders": "持有人",
    "holders_missing": "持有人缺失",
    "visiting": "热度",
    "visiting_missing": "热度缺失",
    "volume_1h": "成交量",
    "volume_missing": "成交量缺失",
    "volume_mc_ratio": "量比市值",
    "too_new": "过新",
    "too_old": "过旧",
    "platform": "平台",
    "platform_missing": "平台缺失",
    "mc_extension": "市值扩张",
    "mc_extension_soft": "市值扩张(软)",
    "loss_cooldown": "亏损冷却",
    "post_close_cooldown": "平仓冷却",
    "cooldown": "告警冷却",
    "cooldown_same_type": "同源冷却",
    "cooldown_cross_source": "跨源冷却",
    "max_concurrent_positions": "持仓上限",
    "no_price": "无有效价格",
    "safety_fetch": "安全查询失败",
    "safety": "安全",
    "safety_wash": "安全·洗盘",
    "safety_rug": "安全·Rug",
    "safety_bundler": "安全·Bundler",
    "safety_rat": "安全·老鼠仓",
    "safety_unknown_profile": "安全·未知档案",
    "safety_honeypot": "安全·蜜罐",
    "safety_honeypot_missing": "安全·蜜罐缺失",
    "safety_mint": "安全·Mint",
    "safety_freeze": "安全·冻结",
    "safety_renounced": "安全·未弃权",
    "safety_renounced_missing": "安全·弃权缺失",
    "safety_open_source": "安全·未开源",
    "safety_open_source_missing": "安全·开源缺失",
    "safety_tax": "安全·税",
    "executor_error": "执行异常",
    "filter": "筛选",
}


def gmgn_link(chain: str, address: str) -> str:
    return GMGN_URL.get(chain, "https://gmgn.ai/token/{addr}").format(addr=address)


def gmgn_keyboard(chain: str, address: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="打开 GMGN", url=gmgn_link(chain, address))]
        ]
    )


def reject_reason_label(reason: str) -> str:
    return REASON_LABELS.get(reason, reason)


def reject_source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def format_relative_age(ts: float | None, *, now: float | None = None) -> str:
    if ts is None or ts <= 0:
        return "—"
    now = time.time() if now is None else now
    return format_duration(max(0.0, now - ts))


def format_duration(sec: float | None) -> str:
    if sec is None:
        return "—"
    sec = max(0.0, float(sec))
    if sec < 60:
        return f"{sec:.0f}s"
    if sec < 3600:
        return f"{sec / 60:.0f}m"
    if sec < 86400:
        return f"{sec / 3600:.1f}h"
    return f"{sec / 86400:.1f}d"


def format_latency(sec: float | None) -> str:
    if sec is None:
        return "—"
    if sec < 10:
        return f"{sec:.1f}s"
    return f"{sec:.0f}s"


def render_card(
    cand: TokenCandidate,
    paper: ExecResult | None = None,
    *,
    latency_sec: float | None = None,
    paper_status: str | None = None,
) -> str:
    """Unified signal-push card (plain text)."""
    sym = cand.symbol or "未知"
    title = f"📡 [{cand.chain_tag}] 信号推送  ${sym}"
    if cand.dual_source:
        title += "  ·  双源"
    lines = [
        title,
        "",
        cand.address,
        "",
        f"🕐 开盘 {format_relative_age(cand.open_timestamp)}",
        _mc_line(cand),
        f"💧 流动性 {_usd_compact(cand.liquidity)}  ·  👥 {_num(cand.holder_count)}",
        f"📊 Top10 {_pct(cand.top10_rate)}  ·  🔥 {_num(cand.visiting_count)}",
        "",
        _safety_line(cand),
        "",
        f"⏱ 延迟 {format_latency(latency_sec)}",
        _paper_line(paper, paper_status=paper_status),
    ]
    return "\n".join(lines)


def append_news_line(card: str, news_line: str | None) -> str:
    if not news_line:
        return card
    lines = [line for line in card.splitlines() if not line.startswith("📰")]
    lines.append(news_line)
    return "\n".join(lines)


def render_paper_event(ev: PaperTradeEvent) -> str:
    tag = _chain_tag(ev.chain)
    sym = ev.symbol or ev.token[:8]
    reason = CLOSE_REASON_LABELS.get(ev.reason, ev.reason)
    icon = CLOSE_ICONS.get(ev.reason, "📉")
    pnl_s = _pnl(ev.pnl)

    if ev.kind == "stage1":
        lines = [
            f"{icon} [{tag}] 回本减仓  ${sym}  {pnl_s}",
            "",
            ev.token,
            "",
        ]
        if ev.entry_mc is not None and ev.exit_mc is not None and ev.entry_mc > 0:
            chg = (ev.exit_mc / ev.entry_mc) - 1.0
            lines.append(
                f"💰 入场 {_usd_compact(ev.entry_mc)} → 减仓 {_usd_compact(ev.exit_mc)}  ({_pct(chg)})"
            )
        lines.append(f"💰 回收约 {_usd_compact(ev.qty * ev.fill_price)}  ·  剩余仓继续")
        lines.append("📌 成本已上移")
        return "\n".join(lines)

    lines = [
        f"{icon} [{tag}] {reason}  ${sym}  {pnl_s}",
        "",
        ev.token,
        "",
    ]
    if ev.entry_mc is not None and ev.exit_mc is not None and ev.entry_mc > 0:
        chg = (ev.exit_mc / ev.entry_mc) - 1.0
        lines.append(
            f"💰 入场 {_usd_compact(ev.entry_mc)} → 平仓 {_usd_compact(ev.exit_mc)}  ({_pct(chg)})"
        )
        extra = f"名义 {_usd_compact(ev.notional_usd)}"
        if ev.hold_sec is not None:
            extra = f"⏱ 持仓 {format_duration(ev.hold_sec)}  ·  {extra}"
        if ev.reason == "trail" and ev.peak_mc is not None:
            extra = f"📈 峰值 {_usd_compact(ev.peak_mc)}  ·  {extra}"
        lines.append(extra)
    else:
        lines.append(f"标记价 {_price(ev.mark)}  ·  盈亏 {pnl_s}")
        lines.append(f"名义 {_usd_compact(ev.notional_usd)}  ·  入场 {_price(ev.entry_price)}")
    return "\n".join(lines)


def render_positions(
    rows: list,
    *,
    quotes: dict[tuple[str, str], dict[str, float | None]] | None = None,
) -> str:
    quotes = quotes or {}
    if not rows:
        return "📋 持仓 0 笔\n\n当前无模拟持仓。\n用 /stats 看历史盈亏。"

    by_chain: dict[str, list] = {}
    for row in rows:
        by_chain.setdefault(str(row["chain"]), []).append(row)

    total_n = len(rows)
    total_notional = sum(float(r["notional_usd"] or 0) for r in rows)
    lines = [f"📋 持仓 {total_n} 笔  ·  名义 {_usd_compact(total_notional)}", ""]

    for chain, chain_rows in by_chain.items():
        tag = _chain_tag(chain)
        chain_notional = sum(float(r["notional_usd"] or 0) for r in chain_rows)
        lines.append(f"[{tag}] {len(chain_rows)} 笔  ·  {_usd_compact(chain_notional)}")
        for i, row in enumerate(chain_rows, 1):
            sym = row["symbol"] or row["token"][:8]
            q = quotes.get((row["chain"], row["token"])) or {}
            mark = q.get("price")
            mark_mc = q.get("market_cap")
            keys = row.keys() if hasattr(row, "keys") else row
            open_mark = (
                row["open_mark"]
                if "open_mark" in keys and row["open_mark"] is not None
                else row["entry_price"]
            )
            entry_mc = mc_from_price_ratio(mark_mc, mark, open_mark)
            peak_mc = mc_from_price_ratio(mark_mc, mark, row["peak_price"])
            u_pnl = None
            if mark is not None and row["qty"] and row["cost_basis"]:
                u_pnl = (mark - row["cost_basis"]) * row["qty"]
            chg = None
            if entry_mc and mark_mc and entry_mc > 0:
                chg = (mark_mc / entry_mc) - 1.0
            stage = "已回本" if row["stage1_done"] else "未回本"
            head = f"{i}. ${sym}"
            if chg is not None:
                head += f"  {_pct(chg)}"
            if u_pnl is not None:
                head += f"  ·  浮盈 {_pnl(u_pnl)}"
            lines.append(head)
            lines.append(f"   {row['token']}")
            if entry_mc is not None and mark_mc is not None:
                lines.append(
                    f"   入场 {_usd_compact(entry_mc)} → 现 {_usd_compact(mark_mc)}  ·  峰 {_usd_compact(peak_mc)}  ·  {stage}"
                )
            else:
                lines.append(
                    f"   入场 {_price(open_mark)} → 现 {_price(mark)}  ·  峰 {_price(row['peak_price'])}  ·  {stage}"
                )
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_stats_section(chain: str, summary: dict, recent_closed: list) -> list[str]:
    tag = _chain_tag(chain)
    closed = int(summary.get("closed_count") or 0)
    hard_stops = int(summary.get("hard_stop_count") or 0)
    if closed > 0:
        hs_line = f"硬止损 {hard_stops}/{closed}  ·  {_pct(hard_stops / closed)}"
    else:
        hs_line = "硬止损 —（尚无平仓）"

    win_rate = summary.get("win_rate")
    avg_win = summary.get("avg_win_usd")
    avg_loss = summary.get("avg_loss_usd")
    avg_hold = summary.get("avg_hold_sec")

    win_rate_str = _pct(win_rate) if win_rate is not None else "—"
    win_count = int(summary.get("win_count") or 0)
    loss_count = closed - win_count if closed > 0 else 0
    expectancy_str = "—"
    if avg_win is not None and avg_loss is not None and closed > 0:
        expectancy = (win_count * avg_win + loss_count * avg_loss) / closed
        expectancy_str = _pnl(expectancy)
    avg_hold_str = f"{int(avg_hold // 60)}m" if avg_hold is not None else "—"

    lines = [
        f"[{tag}]",
        f"持仓 {summary.get('open_count', 0)}  ·  名义 {_usd_compact(summary.get('open_notional'))}",
        f"已平 {closed}  ·  已实现 {_pnl(float(summary.get('closed_pnl') or 0))}",
        f"本轮开仓 {summary.get('opened_count', 0)}  ·  跳过开仓 {summary.get('skipped_open_count', 0)}",
        hs_line,
        f"胜率 {win_rate_str}  ·  盈 {win_count} / 亏 {loss_count}",
        f"均盈 {_pnl(avg_win) if avg_win is not None else '—'}  ·  均亏 {_pnl(avg_loss) if avg_loss is not None else '—'}",
        f"期望值 {expectancy_str}  ·  均持仓 {avg_hold_str}",
    ]
    if recent_closed:
        lines.append("最近平仓")
        for row in recent_closed[:5]:
            sym = row["symbol"] or row["token"][:8]
            reason = CLOSE_REASON_LABELS.get(row["close_reason"] or "", row["close_reason"] or "—")
            lines.append(f"· ${sym} {reason} {_pnl(float(row['realized_pnl'] or 0))}")
    return lines


def render_stats(
    summary: dict | None = None,
    recent_closed: list | None = None,
    *,
    per_chain: dict[str, tuple[dict, list]] | None = None,
) -> str:
    """Render per-chain stats. Prefer ``per_chain={name: (summary, closed_rows)}``.

    Legacy ``summary`` + ``recent_closed`` (treated as a single ``sol`` section) remains for tests.
    """
    if per_chain is None:
        per_chain = {"sol": (summary or {}, recent_closed or [])}

    lines = ["📊 模拟统计", ""]
    for name, (summ, closed) in per_chain.items():
        lines.extend(_render_stats_section(name, summ, closed))
        lines.append("")
    lines.append(
        "注：硬止损计数按 close_reason=hard_stop，含 stage1 已盈利后再硬止损的仓位。"
    )
    lines.append("")
    lines.append("用 /reset_paper <sol|bsc|robinhood|all> confirm 清空模拟（持仓/告警/拦截/冷却）")
    return "\n".join(lines)


def render_reset_paper_hint() -> str:
    return "\n".join(
        [
            "⚠️ 将清空模拟数据",
            "",
            "持仓 / 成交 / 快照 / 冷却 / 告警 / 拦截统计都会删除。",
            "请指定链并确认，例如：",
            "/reset_paper sol confirm",
            "/reset_paper bsc confirm",
            "/reset_paper robinhood confirm",
            "/reset_paper all confirm  （清空全部链）",
        ]
    )


def render_reset_paper(deleted: dict[str, int], *, chain: str = "all") -> str:
    tag = "全部链" if chain == "all" else _chain_tag(chain)
    round_id = deleted.get("round_id")
    lines = [
        f"🧹 [{tag}] 模拟已重置",
        "",
        f"仓位行 {deleted.get('paper_positions', 0)}  ·  成交 {deleted.get('paper_fills', 0)}",
        f"跳过开仓 {deleted.get('paper_skip_opens', 0)}  ·  快照 {deleted.get('snapshots', 0)}",
        f"冷却 {deleted.get('cooldowns', 0)}  ·  告警 {deleted.get('alerts', 0)}  ·  拦截 {deleted.get('reject_counts', 0)}",
    ]
    if round_id:
        lines.append("")
        lines.append(f"📦 旧数据已归档：round #{round_id}（用 /rounds 查询历史轮次）")
    lines.append("")
    lines.append("用 /stats 查看新一轮统计。")
    return "\n".join(lines)


def render_rounds(
    rows: list,
    *,
    detail: list[dict] | None = None,
    recent_closed: list | None = None,
) -> str:
    """Archived experiment rounds overview; optional per-chain detail of one round."""
    if not rows and detail is None:
        return "📦 归档轮次\n\n暂无历史轮次（/reset_paper 后才会有归档）。"
    lines = ["📦 归档轮次", ""]
    if detail is None:
        for row in rows:
            pnl = float(row["closed_pnl"] or 0)
            scope = "全部链" if str(row["reset_chain"]) == "all" else _chain_tag(str(row["reset_chain"]))
            lines.append(
                f"· round #{row['round_id']} [{scope}] {format_duration(time.time() - float(row['reset_at']))}前  "
                f"仓位 {row['positions']} (平 {row['closed_count']} / 在持 {row['open_count']})  "
                f"已实现 {_pnl(pnl)}"
            )
        lines.append("")
        lines.append("用 /rounds <id> 查看某轮详情（例如 /rounds 2）。")
    else:
        rid = detail[0]["round_id"] if detail else rows[0]["round_id"]
        lines.append(f"round #{rid} 详情")
        for d in detail:
            chain_tag = "全部" if d["chain"] is None else _chain_tag(d["chain"])
            wr = f"{d['win_rate'] * 100:.0f}%" if d["win_rate"] is not None else "—"
            lines.append(
                f"· [{chain_tag}] 平 {d['closed_count']} / 在持 {d['open_count']}  "
                f"已实现 {_pnl(d['closed_pnl'])}  胜率 {wr}  "
                f"硬止损 {d['hard_stop_count']}  均赢 {_usd_compact(d['avg_win_usd'])}  均亏 {_usd_compact(d['avg_loss_usd'])}"
            )
        if recent_closed:
            lines.append("")
            lines.append("最近平仓")
            for row in recent_closed[:5]:
                sym = row["symbol"] or row["token"][:8]
                reason = CLOSE_REASON_LABELS.get(row["close_reason"] or "", row["close_reason"] or "—")
                lines.append(f"· ${sym} {reason} {_pnl(float(row['realized_pnl'] or 0))}")
    return "\n".join(lines)


def render_rejects(rows: list) -> str:
    if not rows:
        return "🚫 拦截 Top\n\n暂无拦截统计。"
    lines = ["🚫 拦截 Top", ""]
    for row in rows:
        src = reject_source_label(str(row["source"]))
        reason = reject_reason_label(str(row["reason"]))
        lines.append(f"· [{row['chain']}] {src} / {reason} × {row['count']}")
    return "\n".join(lines)


def render_status(
    *,
    chain_rows: list[dict] | None = None,
    enabled_chains: list[str] | None = None,
    open_count: int | None = None,
    cooldowns: int | None = None,
    chain_modes: dict[str, str] | None = None,
) -> str:
    """Prefer ``chain_rows``: [{name, mode, open_count, cooldowns}, ...].

    Legacy kwargs (enabled_chains / open_count / cooldowns / chain_modes) remain for older callers.
    """
    if chain_rows is None:
        chain_rows = []
        for name in enabled_chains or []:
            mode = (chain_modes or {}).get(name, "paper")
            chain_rows.append(
                {
                    "name": name,
                    "mode": mode,
                    "open_count": open_count if len(enabled_chains or []) == 1 else 0,
                    "cooldowns": cooldowns if len(enabled_chains or []) == 1 else 0,
                }
            )
        if len(enabled_chains or []) != 1 and open_count is not None:
            # Ambiguous legacy multi-chain total — still show mode list, totals only if single.
            pass

    lines = ["🟢 运行中", ""]
    if not chain_rows:
        lines.append("链 —")
        return "\n".join(lines)
    for row in chain_rows:
        tag = _chain_tag(str(row["name"]))
        lines.append(
            f"[{tag}] {row.get('mode', 'paper')}  ·  持仓 {row.get('open_count', 0)}  ·  冷却 {row.get('cooldowns', 0)}"
        )
    return "\n".join(lines)


def render_alerts(
    rows: list | None = None,
    *,
    per_chain: dict[str, list] | None = None,
) -> str:
    """Prefer ``per_chain`` with up to N alerts already fetched per chain.

    Legacy ``rows`` (flat list) still works and groups by chain for display only.
    """
    if per_chain is None:
        per_chain = {}
        for row in rows or []:
            per_chain.setdefault(str(row["chain"]), []).append(row)

    if not any(per_chain.values()):
        return "📨 最近告警\n\n暂无告警记录。"

    lines = ["📨 最近告警", ""]
    for chain, chain_rows in per_chain.items():
        if not chain_rows:
            continue
        lines.append(f"[{_chain_tag(chain)}]")
        for row in chain_rows:
            sym = "?"
            exec_status = ""
            dual = ""
            try:
                payload = json.loads(row["payload_json"] or "{}")
                sym = payload.get("symbol") or "?"
                st = payload.get("exec_status")
                if st == "opened":
                    exec_status = "  ✅开仓"
                elif st == "skipped_open":
                    exec_status = "  ⏭跳过"
                elif st == "blocked_max_positions":
                    exec_status = "  ⛔满仓"
                if payload.get("dual_source"):
                    dual = "  ·双源"
            except Exception:  # noqa: BLE001
                pass
            ts = datetime.fromtimestamp(row["created_at"], tz=timezone.utc).strftime("%m-%d %H:%M")
            lines.append(f"· {ts}  ${sym}{exec_status}{dual}")
            lines.append(f"  {row['token']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_help(
    app_cfg: AppConfig,
    *,
    enabled_chains: list[str] | None = None,
    include_reset: bool = True,
) -> str:
    chains = enabled_chains or [n for n, c in app_cfg.chains.items() if c.enabled]
    cmd_line = "命令：/positions /stats /rejects /alerts /status /rounds /chatid"
    if include_reset:
        cmd_line += " /reset_paper"
    lines = [
        "📖 LumiBot",
        "",
        "推送：过门后信号推送 + 模拟开仓",
        cmd_line,
    ]
    for name in chains:
        cfg = app_cfg.chains.get(name)
        if cfg is None:
            continue
        s = cfg.strategy
        slip = f"买 {_pct(cfg.execution.slippage_buy_pct)} / 卖 {_pct(cfg.execution.slippage_sell_pct)}"
        lines.extend(
            [
                "",
                f"[{_chain_tag(name)}] 规则",
                f"· 名义 {_usd_compact(s.notional_usd)}，滑点 {slip}",
                f"· 硬止损：相对开仓标记 {_pct(s.hard_stop_pct)}",
                (
                    f"· 回本触发 {_pct(s.stage1_tp_pct)} 相对买入成本（含买滑点）；"
                    f"减仓 {'比例 ' + _pct(s.stage1_sell_ratio) if s.stage1_sell_mode == 'ratio' else '回本名义'}；"
                    f"剩余峰值回撤 {_pct(s.trail_drawdown_pct)} 平仓；"
                    f"超时 {format_duration(s.timeout_hours * 3600)}"
                ),
                (
                    f"· 亏损平仓后再入场 {format_duration(s.loss_cooldown_min * 60)}；"
                    f"普通平仓后再入场 {format_duration(s.post_close_cooldown_min * 60)}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "· 开仓/推送指标 = 过门后重拉的实时 token 快照（筛选用当时快照，不二次门控）",
            "· ⏱ 延迟 = 本机见到该条 → 发出前的处理耗时（含过门重拉；不含轮询等待）",
            "· /stats /status /positions /alerts 按链分节展示，不混算合计",
        ]
    )
    if include_reset:
        lines.append(
            "· /reset_paper <sol|bsc|robinhood|all> confirm 清空对应链的本轮模拟统计（旧数据归档，/rounds 可查）"
        )
    else:
        lines.append("· /reset_paper 仅限私聊控制台（群组不可用）")
    return "\n".join(lines)


def render_unknown_command() -> str:
    return "📖 未知指令\n\n发送 /help 查看可用命令。"


def _mc_line(cand: TokenCandidate) -> str:
    if (
        cand.source == Source.SIGNAL
        and cand.trigger_mc is not None
        and cand.trigger_mc > 0
        and cand.market_cap is not None
    ):
        chg = (cand.market_cap / cand.trigger_mc) - 1.0
        return (
            f"💰 市值 {_usd_compact(cand.market_cap)} → 触发 {_usd_compact(cand.trigger_mc)}"
            f"  ({_pct(chg)})"
        )
    return f"💰 市值 {_usd_compact(cand.market_cap)}"


def _safety_line(cand: TokenCandidate) -> str:
    safety = cand.safety
    if safety is None:
        return "🛡 安全 通过"
    parts: list[str] = ["🛡 安全 通过"]
    for w in safety.warnings:
        parts.append(f"⚠ {WARN_LABELS.get(w, w)}")
    if safety.wash_trading is True:
        parts.append("⚠ 洗盘")
    risk_bits: list[str] = []
    if safety.rug_ratio is not None and safety.rug_ratio > 0:
        risk_bits.append(f"Rug {_pct(safety.rug_ratio)}")
    if safety.bundler_rate is not None and safety.bundler_rate > 0:
        risk_bits.append(f"Bundler {_pct(safety.bundler_rate)}")
    if safety.rat_rate is not None and safety.rat_rate > 0:
        risk_bits.append(f"老鼠仓 {_pct(safety.rat_rate)}")
    if risk_bits:
        parts.append(" · ".join(risk_bits))
    return "  ·  ".join(parts)


def _paper_line(paper: ExecResult | None, *, paper_status: str | None = None) -> str:
    if paper_status == "opening":
        return "⏳ 开仓中"
    if paper_status == "precheck_skipped_open":
        return "↪️ 未新开"
    if paper_status == "executor_error":
        return "⛔ 执行异常"
    if paper is None:
        return "—"
    if paper.status == "opened":
        return f"✅ 已开仓 {_usd_compact(paper.notional_usd)}"
    if paper.status == "skipped_open":
        return "⏭ 未新开（已有仓）"
    if paper.status == "blocked_max_positions":
        return "⛔ 未新开（已达持仓上限）"
    if paper.status == "no_price":
        return "⛔ 未开仓（无价格）"
    if paper.status == "blocked_live":
        return "⛔ 实盘已阻断"
    if paper.status == "noop":
        return "—"
    return f"模拟 {paper.status}"


def _usd_compact(v: float | None) -> str:
    if v is None:
        return "—"
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs_v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:.2f}"


def _num(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 1:
        return f"{v:.4g}"
    return f"{v:.6g}"


def _price(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1:
        return f"{v:.6g}"
    return f"{v:.8g}"


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def _pnl(v: float) -> str:
    if v >= 0:
        return f"+${v:.2f}"
    return f"-${abs(v):.2f}"


class TelegramNotifier:
    def __init__(self, token: str, chat_ids: list[int]) -> None:
        self.chat_ids = chat_ids
        self._bot = Bot(token=token)

    @property
    def bot(self) -> Bot:
        return self._bot

    async def close(self) -> None:
        await self._bot.session.close()

    async def send_text(
        self,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        disable_preview: bool = True,
    ) -> tuple[bool, bool, list[tuple[int, int]]]:
        if not self.chat_ids:
            return False, False, []
        ok = 0
        fail = 0
        message_ids: list[tuple[int, int]] = []
        for chat_id in self.chat_ids:
            try:
                msg = await self._bot.send_message(
                    chat_id,
                    text,
                    disable_web_page_preview=disable_preview,
                    parse_mode=None,
                    reply_markup=reply_markup,
                )
                message_ids.append((chat_id, msg.message_id))
                ok += 1
            except Exception:  # noqa: BLE001
                fail += 1
                logger.exception("telegram send failed chat_id=%s", chat_id)
        return ok > 0, fail == 0, message_ids

    async def edit_text(
        self,
        text: str,
        message_ids: list[tuple[int, int]],
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        disable_preview: bool = True,
    ) -> tuple[bool, bool]:
        if not message_ids:
            return False, False
        ok = 0
        fail = 0
        for chat_id, message_id in message_ids:
            try:
                await self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    disable_web_page_preview=disable_preview,
                    parse_mode=None,
                    reply_markup=reply_markup,
                )
                ok += 1
            except Exception:  # noqa: BLE001
                fail += 1
                logger.exception("telegram edit failed chat_id=%s message_id=%s", chat_id, message_id)
        return ok > 0, fail == 0

    async def send_candidate(
        self,
        cand: TokenCandidate,
        paper: ExecResult | None = None,
        *,
        latency_sec: float | None = None,
        paper_status: str | None = None,
    ) -> tuple[bool, bool, list[tuple[int, int]]]:
        return await self.send_text(
            render_card(cand, paper=paper, latency_sec=latency_sec, paper_status=paper_status),
            reply_markup=gmgn_keyboard(cand.chain, cand.address),
            disable_preview=True,
        )

    async def edit_candidate(
        self,
        cand: TokenCandidate,
        paper: ExecResult | None = None,
        *,
        latency_sec: float | None = None,
        paper_status: str | None = None,
        message_ids: list[tuple[int, int]],
    ) -> tuple[bool, bool]:
        return await self.edit_text(
            render_card(cand, paper=paper, latency_sec=latency_sec, paper_status=paper_status),
            message_ids,
            reply_markup=gmgn_keyboard(cand.chain, cand.address),
            disable_preview=True,
        )

    async def edit_candidate_with_news(
        self,
        cand: TokenCandidate,
        paper: ExecResult | None = None,
        *,
        latency_sec: float | None = None,
        paper_status: str | None = None,
        message_ids: list[tuple[int, int]],
        news_line: str | None = None,
    ) -> tuple[bool, bool]:
        return await self.edit_text(
            append_news_line(
                render_card(
                    cand,
                    paper=paper,
                    latency_sec=latency_sec,
                    paper_status=paper_status,
                ),
                news_line,
            ),
            message_ids,
            reply_markup=gmgn_keyboard(cand.chain, cand.address),
            disable_preview=True,
        )

    async def send_paper_event(self, ev: PaperTradeEvent) -> tuple[bool, bool]:
        ok, all_ok, _ = await self.send_text(
            render_paper_event(ev),
            reply_markup=gmgn_keyboard(ev.chain, ev.token),
            disable_preview=True,
        )
        return ok, all_ok
