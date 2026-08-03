from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from lumibot.exec_types import ExecResult, PaperTradeEvent
from lumibot.models import NormalizedSafety, Source, TokenCandidate

logger = logging.getLogger(__name__)

GMGN_URL = {
    "sol": "https://gmgn.ai/sol/token/{addr}",
    "bsc": "https://gmgn.ai/bsc/token/{addr}",
    "robinhood": "https://gmgn.ai/rh/token/{addr}",
}

SIGNAL_TYPE_LABELS = {
    12: "聪明钱",
    20: "KOL",
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


def gmgn_link(chain: str, address: str) -> str:
    return GMGN_URL.get(chain, "https://gmgn.ai/token/{addr}").format(addr=address)


def gmgn_keyboard(chain: str, address: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="打开 GMGN", url=gmgn_link(chain, address))]
        ]
    )


def render_card(cand: TokenCandidate, paper: ExecResult | None = None) -> str:
    """Compact Chinese memebot-style alert (plain text)."""
    sym = cand.symbol or "未知"
    name = (cand.name or "").strip()
    token_line = f"${sym}"
    if name and name != sym:
        token_line += f"（{name}）"

    metrics1 = f"市值 {_usd_compact(cand.market_cap)} | 流动性 {_usd_compact(cand.liquidity)}"
    if cand.source == Source.SIGNAL and cand.trigger_mc is not None:
        metrics1 += f" | 触发市值 {_usd_compact(cand.trigger_mc)}"
    metrics2 = (
        f"持有人 {_num(cand.holder_count)} | 热度 {_num(cand.visiting_count)} | "
        f"Top10 {_pct(cand.top10_rate)}"
    )
    price_line = f"价格 {_price(cand.price)}"
    if cand.platform:
        price_line += f" | 平台 {cand.platform}"

    safety = "安全 " + " ".join(_safety_badges(cand.safety, cand.chain))
    risk = _risk_line(cand.safety)
    strategy = "策略 名义$20 | 硬止损相对开仓标记-20% | 回本+30% | 回撤30% | 超时4h"

    lines = [
        _source_title(cand),
        "",
        token_line,
        cand.address,
        "",
        price_line,
        metrics1,
        metrics2,
        "",
        safety,
    ]
    if risk:
        lines.append(risk)
    lines.extend(
        [
            "",
            strategy,
            _paper_line(paper),
            "",
            "命令 /positions /stats /rejects /help",
        ]
    )
    return "\n".join(lines)


def render_paper_event(ev: PaperTradeEvent) -> str:
    tag = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(ev.chain, ev.chain.upper())
    sym = ev.symbol or ev.token[:8]
    reason = CLOSE_REASON_LABELS.get(ev.reason, ev.reason)
    pnl_s = _pnl(ev.pnl)
    if ev.kind == "stage1":
        title = f"[{tag}] 模拟 · 回本减仓"
        body = (
            f"${sym}\n"
            f"{ev.token}\n"
            f"\n"
            f"卖出 {_num(ev.qty)} @ {_price(ev.fill_price)}\n"
            f"回收约 {_usd_compact(ev.qty * ev.fill_price)} | 盈亏 {pnl_s}\n"
            f"剩余仓 {_num(ev.remaining_qty)} | 成本上移 {_price(ev.fill_price)}\n"
            f"入场参考 {_price(ev.entry_price)}"
        )
        return f"{title}\n\n{body}"

    title = f"[{tag}] 模拟 · {reason}"
    body = (
        f"${sym}\n"
        f"{ev.token}\n"
        f"\n"
        f"平仓 {_num(ev.qty)} @ {_price(ev.fill_price)}\n"
        f"标记价 {_price(ev.mark)} | 盈亏 {pnl_s}\n"
        f"名义 {_usd_compact(ev.notional_usd)} | 入场 {_price(ev.entry_price)}"
    )
    return f"{title}\n\n{body}"


def render_positions(
    rows: list,
    *,
    quotes: dict[tuple[str, str], dict[str, float | None]] | None = None,
) -> str:
    """Render open papers using market caps (not token prices)."""
    quotes = quotes or {}
    if not rows:
        return "当前无模拟持仓。\n用 /stats 看历史盈亏。"
    lines = ["【模拟持仓】", ""]
    for i, row in enumerate(rows, 1):
        sym = row["symbol"] or row["token"][:8]
        tag = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(row["chain"], row["chain"].upper())
        q = quotes.get((row["chain"], row["token"])) or {}
        mark = q.get("price")
        mark_mc = q.get("market_cap")
        entry_ref = row["open_mark"] if "open_mark" in row.keys() and row["open_mark"] is not None else row["entry_price"]
        entry_mc = _mc_from_price_ratio(mark_mc, mark, entry_ref)
        peak_mc = _mc_from_price_ratio(mark_mc, mark, row["peak_price"])
        u_pnl = None
        if mark is not None and row["qty"] and row["cost_basis"]:
            u_pnl = (mark - row["cost_basis"]) * row["qty"]
        chg = None
        if entry_mc and mark_mc and entry_mc > 0:
            chg = (mark_mc / entry_mc) - 1.0
        stage = "已回本" if row["stage1_done"] else "未回本"
        lines.append(f"{i}. [{tag}] ${sym}")
        lines.append(f"   {row['token']}")
        lines.append(
            f"   入场市值 {_usd_compact(entry_mc)} | 当前 {_usd_compact(mark_mc)} | 峰值 {_usd_compact(peak_mc)}"
        )
        lines.append(
            f"   名义 {_usd_compact(row['notional_usd'])} | {stage}"
            + (f" | 涨跌 {_pct(chg)}" if chg is not None else "")
            + (f" | 浮盈 {_pnl(u_pnl)}" if u_pnl is not None else "")
        )
        lines.append("")
    lines.append("出场：硬止损相对开仓标记-20% / 回本+30% / 回撤30% / 超时4h")
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
        "【模拟统计】",
        "",
        f"持仓中：{summary.get('open_count', 0)} 笔 | 名义 {_usd_compact(summary.get('open_notional'))}",
        f"已平仓：{summary.get('closed_count', 0)} 笔 | 已实现 {_pnl(float(summary.get('closed_pnl') or 0))}",
        f"告警新开：{summary.get('opened_count', 0)} | 已有仓跳过：{summary.get('skipped_open_count', 0)}",
        "",
    ]
    if recent_closed:
        lines.append("最近平仓：")
        for row in recent_closed[:8]:
            sym = row["symbol"] or row["token"][:8]
            tag = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(
                row["chain"], row["chain"].upper()
            )
            reason = CLOSE_REASON_LABELS.get(row["close_reason"] or "", row["close_reason"] or "—")
            lines.append(
                f"· [{tag}] ${sym} {reason} {_pnl(float(row['realized_pnl'] or 0))}"
            )
    else:
        lines.append("暂无平仓记录。")
    return "\n".join(lines)


def render_rejects(rows: list) -> str:
    if not rows:
        return "暂无拦截统计。"
    lines = ["【拦截统计】Top 原因", ""]
    for row in rows:
        lines.append(
            f"· [{row['chain']}] {row['source']} / {row['reason']} × {row['count']}"
        )
    return "\n".join(lines)


def render_status(*, enabled_chains: list[str], open_count: int, cooldowns: int, mode: str) -> str:
    return "\n".join(
        [
            "【运行状态】",
            "",
            f"启用链：{', '.join(enabled_chains) or '—'}",
            f"执行模式：{mode}",
            f"模拟持仓：{open_count}",
            f"生效冷却：{cooldowns}",
            "",
            "命令：/positions /stats /rejects /alerts /help",
        ]
    )


def render_alerts(rows: list) -> str:
    if not rows:
        return "暂无告警记录。"
    lines = ["【最近告警】", ""]
    for row in rows:
        sym = "?"
        try:
            payload = json.loads(row["payload_json"] or "{}")
            sym = payload.get("symbol") or "?"
        except Exception:  # noqa: BLE001
            pass
        ts = datetime.fromtimestamp(row["created_at"], tz=timezone.utc).strftime("%m-%d %H:%M")
        tag = {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(row["chain"], row["chain"].upper())
        lines.append(f"· {ts} UTC [{tag}] ${sym} {row['source_key']}")
        lines.append(f"  {row['token'][:20]}…")
    return "\n".join(lines)


def render_help() -> str:
    return "\n".join(
        [
            "【LumiBot 帮助】",
            "",
            "自动推送：聪明钱/KOL/热门趋势 → 筛选安全 → 模拟开仓",
            "",
            "/positions  当前模拟持仓",
            "/stats      模拟盈亏统计",
            "/rejects    筛选拦截原因",
            "/alerts     最近告警",
            "/status     运行状态",
            "/help       本帮助",
            "",
            "模拟规则：名义$20，买/卖滑点按链，硬止损相对开仓标记-20%，",
            "回本+30%减仓，峰值回撤30%，超时4h。",
            "过门=推送+开仓；硬止损后再入场冷却3h，普通平仓45m。",
        ]
    )


def _paper_line(paper: ExecResult | None) -> str:
    if paper is None:
        return "模拟 —"
    if paper.status == "opened":
        mark = paper.open_mark if paper.open_mark is not None else paper.mark
        stop_pct = paper.hard_stop_pct if paper.hard_stop_pct is not None else -0.20
        slip = f"买滑点 {_pct(paper.buy_slip)}" if paper.buy_slip is not None else "买滑点 —"
        return (
            f"模拟 ✅已开仓 {_usd_compact(paper.notional_usd)}\n"
            f"开仓标记 {_price(mark)} | 成本 {_price(paper.entry_price)}（{slip}）\n"
            f"硬止损相对开仓标记 {_pct(stop_pct)}"
        )
    if paper.status == "skipped_open":
        return "模拟 ⏭未新开（同币已有仓位，仍推送）"
    if paper.status == "no_price":
        return "模拟 ⏭未开仓（无价格）"
    if paper.status == "blocked_live":
        return "实盘 ⛔已阻断"
    if paper.status == "noop":
        return "实盘 占位（未下单）"
    return f"模拟 {paper.status}"


def _source_title(cand: TokenCandidate) -> str:
    tag = cand.chain_tag
    if cand.source == Source.TRENDING:
        return f"[{tag}] 热门趋势"
    label = SIGNAL_TYPE_LABELS.get(cand.signal_type or -1, "信号")
    if cand.signal_type is not None:
        return f"[{tag}] {label} · 类型{cand.signal_type}"
    return f"[{tag}] {label}"


def _safety_badges(safety: NormalizedSafety | None, chain: str) -> list[str]:
    if safety is None:
        return ["✅已通过"]

    badges: list[str] = []
    profile_sol = chain == "sol"

    if profile_sol:
        if safety.renounced_mint is not None:
            badges.append("✅Mint放弃" if safety.renounced_mint else "❌Mint未放弃")
        if safety.renounced_freeze is not None:
            badges.append("✅冻结放弃" if safety.renounced_freeze else "❌冻结未放弃")
    else:
        if safety.honeypot is not None:
            badges.append("❌蜜罐" if safety.honeypot else "✅非蜜罐")
        if safety.renounced is not None:
            badges.append("✅弃权" if safety.renounced else "❌未弃权")
        if safety.open_source is not None:
            badges.append("✅开源" if safety.open_source else "❌未开源")
        if safety.buy_tax is not None or safety.sell_tax is not None:
            badges.append(f"税{_pct(safety.buy_tax)}/{_pct(safety.sell_tax)}")

    if safety.wash_trading is True:
        badges.append("❌洗盘")
    for w in safety.warnings:
        badges.append(f"⚠{WARN_LABELS.get(w, w)}")

    if not badges:
        badges.append("✅已通过" if not safety.hard_fail else "❌拦截")
    return badges


def _risk_line(safety: NormalizedSafety | None) -> str | None:
    if safety is None:
        return None
    parts: list[str] = []
    if safety.rug_ratio is not None:
        parts.append(f"Rug {_pct(safety.rug_ratio)}")
    if safety.bundler_rate is not None:
        parts.append(f"Bundler {_pct(safety.bundler_rate)}")
    if safety.rat_rate is not None:
        parts.append(f"老鼠仓 {_pct(safety.rat_rate)}")
    if not parts:
        return None
    return "风险 " + " | ".join(parts)


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
        self, cand: TokenCandidate, paper: ExecResult | None = None
    ) -> tuple[bool, bool]:
        return await self.send_text(
            render_card(cand, paper=paper),
            reply_markup=gmgn_keyboard(cand.chain, cand.address),
            disable_preview=True,
        )

    async def send_paper_event(self, ev: PaperTradeEvent) -> tuple[bool, bool]:
        return await self.send_text(
            render_paper_event(ev),
            reply_markup=gmgn_keyboard(ev.chain, ev.token),
            disable_preview=True,
        )
