from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from lumibot.exec_types import ExecResult, PaperTradeEvent
from lumibot.models import Source, TokenCandidate

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
    "timeout": "超时平仓",
    "stage1_full": "回本全平",
    "stage1": "回本减仓",
    "close": "平仓",
}

CLOSE_ICONS = {
    "hard_stop": "📉",
    "trail": "📉",
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
    "top10": "Top10",
    "top10_missing": "Top10缺失",
    "holders": "持有人",
    "holders_missing": "持有人缺失",
    "visiting": "热度",
    "visiting_missing": "热度缺失",
    "platform": "平台",
    "platform_missing": "平台缺失",
    "mc_extension": "市值扩张",
    "mc_extension_soft": "市值扩张(软)",
    "loss_cooldown": "硬止损冷却",
    "post_close_cooldown": "平仓冷却",
    "cooldown": "告警冷却",
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
) -> str:
    """Unified signal-push card (plain text)."""
    sym = cand.symbol or "未知"
    lines = [
        f"📡 [{cand.chain_tag}] 信号推送  ${sym}",
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
        _paper_line(paper),
    ]
    return "\n".join(lines)


def render_paper_event(ev: PaperTradeEvent) -> str:
    tag = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(ev.chain, ev.chain.upper())
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
    lines = [f"📋 持仓 {len(rows)} 笔  ·  名义 {_usd_compact(sum(float(r['notional_usd'] or 0) for r in rows))}", ""]
    for i, row in enumerate(rows, 1):
        sym = row["symbol"] or row["token"][:8]
        tag = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(row["chain"], row["chain"].upper())
        q = quotes.get((row["chain"], row["token"])) or {}
        mark = q.get("price")
        mark_mc = q.get("market_cap")
        keys = row.keys() if hasattr(row, "keys") else row
        open_mark = (
            row["open_mark"]
            if "open_mark" in keys and row["open_mark"] is not None
            else row["entry_price"]
        )
        entry_mc = _mc_from_price_ratio(mark_mc, mark, open_mark)
        peak_mc = _mc_from_price_ratio(mark_mc, mark, row["peak_price"])
        u_pnl = None
        if mark is not None and row["qty"] and row["cost_basis"]:
            u_pnl = (mark - row["cost_basis"]) * row["qty"]
        chg = None
        if entry_mc and mark_mc and entry_mc > 0:
            chg = (mark_mc / entry_mc) - 1.0
        stage = "已回本" if row["stage1_done"] else "未回本"
        head = f"{i}. [{tag}] ${sym}"
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


def _mc_from_price_ratio(
    mark_mc: float | None, mark_price: float | None, ref_price: float | None
) -> float | None:
    if mark_mc is None or mark_price is None or ref_price is None:
        return None
    if mark_price <= 0 or ref_price <= 0:
        return None
    return mark_mc * (ref_price / mark_price)


def render_stats(summary: dict, recent_closed: list) -> str:
    lines = [
        "📊 模拟统计",
        "",
        f"持仓 {summary.get('open_count', 0)}  ·  名义 {_usd_compact(summary.get('open_notional'))}",
        f"已平 {summary.get('closed_count', 0)}  ·  已实现 {_pnl(float(summary.get('closed_pnl') or 0))}",
        f"新开 {summary.get('opened_count', 0)}  ·  跳过 {summary.get('skipped_open_count', 0)}",
        "",
    ]
    if recent_closed:
        lines.append("最近平仓")
        for row in recent_closed[:8]:
            sym = row["symbol"] or row["token"][:8]
            reason = CLOSE_REASON_LABELS.get(row["close_reason"] or "", row["close_reason"] or "—")
            lines.append(f"· ${sym} {reason} {_pnl(float(row['realized_pnl'] or 0))}")
    else:
        lines.append("暂无平仓记录。")
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


def render_status(*, enabled_chains: list[str], open_count: int, cooldowns: int, mode: str) -> str:
    return "\n".join(
        [
            "🟢 运行中",
            "",
            f"链 {', '.join(enabled_chains) or '—'}  ·  {mode}",
            f"持仓 {open_count}  ·  冷却 {cooldowns}",
        ]
    )


def render_alerts(rows: list) -> str:
    if not rows:
        return "📨 最近告警\n\n暂无告警记录。"
    lines = ["📨 最近告警", ""]
    for row in rows:
        sym = "?"
        exec_status = ""
        try:
            payload = json.loads(row["payload_json"] or "{}")
            sym = payload.get("symbol") or "?"
            st = payload.get("exec_status")
            if st == "opened":
                exec_status = "  ✅开仓"
            elif st == "skipped_open":
                exec_status = "  ⏭跳过"
        except Exception:  # noqa: BLE001
            pass
        ts = datetime.fromtimestamp(row["created_at"], tz=timezone.utc).strftime("%m-%d %H:%M")
        tag = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(row["chain"], row["chain"].upper())
        lines.append(f"· {ts}  [{tag}] ${sym}{exec_status}")
        lines.append(f"  {row['token']}")
    return "\n".join(lines)


def render_help() -> str:
    return "\n".join(
        [
            "📖 LumiBot",
            "",
            "推送：过门后信号推送 + 模拟开仓",
            "命令：/positions /stats /rejects /alerts /status",
            "",
            "规则",
            "· 名义 $20，买卖滑点按链",
            "· 硬止损：相对开仓标记 -20%",
            "· 回本 +30% 减仓；峰值回撤 30%；超时 4h",
            "· 硬止损后再入场 3h；普通平仓后再入场 45m",
            "· 开仓/推送指标 = 过门后重拉的实时 token 快照（筛选用当时快照，不二次门控）",
            "· ⏱ 延迟 = 本机见到该条 → 发出前的处理耗时（含过门重拉；不含轮询等待）",
        ]
    )


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


def _paper_line(paper: ExecResult | None) -> str:
    if paper is None:
        return "—"
    if paper.status == "opened":
        return f"✅ 已开仓 {_usd_compact(paper.notional_usd)}"
    if paper.status == "skipped_open":
        return "⏭ 未新开（已有仓）"
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
    ) -> tuple[bool, bool]:
        if not self.chat_ids:
            return False, False
        ok = 0
        fail = 0
        for chat_id in self.chat_ids:
            try:
                await self._bot.send_message(
                    chat_id,
                    text,
                    disable_web_page_preview=disable_preview,
                    parse_mode=None,
                    reply_markup=reply_markup,
                )
                ok += 1
            except Exception:  # noqa: BLE001
                fail += 1
                logger.exception("telegram send failed chat_id=%s", chat_id)
        return ok > 0, fail == 0

    async def send_candidate(
        self,
        cand: TokenCandidate,
        paper: ExecResult | None = None,
        *,
        latency_sec: float | None = None,
    ) -> tuple[bool, bool]:
        return await self.send_text(
            render_card(cand, paper=paper, latency_sec=latency_sec),
            reply_markup=gmgn_keyboard(cand.chain, cand.address),
            disable_preview=True,
        )

    async def send_paper_event(self, ev: PaperTradeEvent) -> tuple[bool, bool]:
        return await self.send_text(
            render_paper_event(ev),
            reply_markup=gmgn_keyboard(ev.chain, ev.token),
            disable_preview=True,
        )
