from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardMarkup,
    Message,
)

from lumibot.config import AppConfig, enabled_chains
from lumibot.db import Database
from lumibot.filters import merge_info_fields
from lumibot.gmgn.client import GmgnClient
from lumibot.models import Source, TokenCandidate
from lumibot.narrative import NarrativeService
from lumibot.safety import evaluate_safety, normalize_security
from lumibot.telegram_notify import (
    gmgn_keyboard,
    render_alerts,
    render_help,
    render_positions,
    render_narrative_block,
    render_query_card,
    render_rejects,
    render_reset_paper,
    render_reset_paper_hint,
    render_rounds,
    render_stats,
    render_status,
    render_unknown_command,
)

logger = logging.getLogger(__name__)

EVM_CA_RE = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
SOLANA_CA_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{40,44}\b")


def _extract_ca(text: str) -> str | None:
    """First contract address in text: EVM 0x+40hex, else Solana base58 40-44."""
    m = EVM_CA_RE.search(text)
    if m:
        return m.group(0)
    m = SOLANA_CA_RE.search(text)
    if m:
        return m.group(0)
    return None


def _chain_candidates(addr: str, app_cfg: AppConfig) -> list[str]:
    """Chain candidates for an address: sol by format, EVM chains per probe order."""
    enabled = enabled_chains(app_cfg)
    if EVM_CA_RE.fullmatch(addr):
        order = app_cfg.global_.ca_query.probe_order if app_cfg.global_.ca_query else ["bsc", "robinhood"]
        return [c for c in order if c in enabled]
    return ["sol"] if "sol" in enabled else []


def _info_has_data(info: dict, addr: str) -> bool:
    """GMGN serves a 200 empty shell (symbol='', address='') for wrong chains.

    A real token resolves with a non-empty symbol and the requested address.
    """
    if info.get("address") and info.get("address") != addr:
        return False
    sym = info.get("symbol") or info.get("token_symbol")
    if sym:
        return True
    if info.get("market_cap") or info.get("mc"):
        return True
    return False


def _as_float(v: object) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _market_cap_from_info(info: dict) -> float | None:
    """market cap = price.price × circulating_supply (token_info omits market_cap)."""
    px = info.get("price")
    price = None
    if isinstance(px, dict):
        price = _as_float(px.get("price"))
    else:
        price = _as_float(px)
    supply = _as_float(info.get("circulating_supply") or info.get("total_supply"))
    if price is None or price <= 0 or supply is None or supply <= 0:
        return None
    return price * supply


async def _query_token(
    client: GmgnClient,
    addr: str,
    app_cfg: AppConfig,
) -> tuple[str | None, TokenCandidate | None, dict | None]:
    """Probe candidate chains and assemble a candidate with info + advisory safety."""
    for chain in _chain_candidates(addr, app_cfg):
        try:
            info = await client.get_token_info(chain, addr)
        except Exception as exc:  # noqa: BLE001
            if "404" in str(exc):
                continue  # wrong chain — try next
            raise  # GMGN down (429/IP ban/network) — let the handler degrade
        if not isinstance(info, dict) or not info or not _info_has_data(info, addr):
            continue
        cand = TokenCandidate(chain=chain, address=addr, source=Source.TRENDING)
        merge_info_fields(cand, info, force_visiting=True)
        # GMGN token_info does NOT return market_cap; compute price × supply.
        if cand.market_cap is None:
            cand.market_cap = _market_cap_from_info(info)
        wts = info.get("wallet_tags_stat")
        if isinstance(wts, dict):
            cand.smart_wallets = _as_float(wts.get("smart_wallets"))
            cand.kol_wallets = _as_float(wts.get("renowned_wallets"))
        chain_cfg = app_cfg.chains.get(chain)
        try:
            sec = await client.get_token_security(chain, addr)
            if chain_cfg is not None:
                cand.safety = evaluate_safety(
                    chain_cfg.safety_profile,
                    normalize_security(sec if isinstance(sec, dict) else {}),
                    chain_cfg.safety,
                )
        except Exception:  # noqa: BLE001 — advisory only, fail open
            logger.warning("ca query security failed chain=%s addr=%s", chain, addr)
        return chain, cand, info
    return None, None, None


async def _handle_ca_message(
    *,
    chat_id: int,
    text: str,
    client: GmgnClient,
    app_cfg: AppConfig,
    throttle: dict[int, float],
    reply: Callable[..., Awaitable[object]],
    narrative: NarrativeService | None = None,
) -> bool:
    """CA-query flow; returns True when the message was consumed."""
    q = app_cfg.global_.ca_query
    if q is None or not q.enabled:
        return False
    addr = _extract_ca(text)
    if not addr:
        return False
    now = time.time()
    if now - throttle.get(chat_id, 0.0) < q.min_interval_sec:
        await reply("⏳ 查询太频繁，请稍后再试。", parse_mode="HTML")
        return True
    throttle[chat_id] = now
    try:
        chain, cand, info = await _query_token(client, addr, app_cfg)
    except Exception:  # noqa: BLE001 — GMGN down/429/IP ban
        logger.exception("ca query failed chat_id=%s addr=%s", chat_id, addr)
        await reply("⚠️ GMGN 暂时不可用，请稍后再试。", parse_mode="HTML")
        return True
    if chain is None or cand is None:
        await reply("🔍 未找到该合约（支持 sol / bsc / robinhood）。", parse_mode="HTML")
        return True
    card = render_query_card(cand)
    sent = await reply(
        card,
        parse_mode="HTML",
        reply_markup=gmgn_keyboard(chain, addr),
    )
    if narrative is not None and sent is not None:
        # Narrative is a slow LLM call: reply first, then enrich via message edit.
        asyncio.create_task(
            _enrich_query_narrative(narrative, cand, info or {}, sent),
            name=f"ca-narrative-{addr}",
        )
    return True


async def _enrich_query_narrative(
    narrative: NarrativeService,
    cand: TokenCandidate,
    info: dict,
    sent: Message,
) -> None:
    """Append the 📚 narrative block to a fresh query reply; fail-open."""
    try:
        line = await narrative.narrative_for(cand, info)
        block = render_narrative_block(info, line)
        if not block:
            return
        await sent.bot.edit_message_text(
            chat_id=sent.chat.id,
            message_id=sent.message_id,
            text=f"{sent.text}\n{block}",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=sent.reply_markup,
        )
    except Exception:  # noqa: BLE001 — pure display
        logger.warning(
            "ca query narrative failed chain=%s token=%s", cand.chain, cand.address
        )

BOT_COMMANDS_COMMON: list[BotCommand] = [
    BotCommand(command="positions", description="当前模拟持仓"),
    BotCommand(command="stats", description="盈亏统计"),
    BotCommand(command="alerts", description="最近告警"),
    BotCommand(command="status", description="运行状态"),
    BotCommand(command="rejects", description="拦截原因 Top"),
    BotCommand(command="rounds", description="历史轮次"),
    BotCommand(command="help", description="帮助与模拟规则"),
    BotCommand(command="start", description="开始使用"),
    BotCommand(command="chatid", description="获取 chat_id（配群用）"),
]

BOT_COMMANDS_PRIVATE_ONLY: list[BotCommand] = [
    BotCommand(command="reset_paper", description="清空模拟（需 confirm）"),
]

# Full menu for private / default scope (includes reset).
BOT_COMMANDS: list[BotCommand] = [*BOT_COMMANDS_COMMON, *BOT_COMMANDS_PRIVATE_ONLY]
# Group menu: same as common — no reset_paper shortcut.
BOT_COMMANDS_GROUP: list[BotCommand] = list(BOT_COMMANDS_COMMON)


async def register_bot_commands(
    bot: Bot,
    *,
    group_chat_ids: list[int] | set[int] | None = None,
    control_chat_ids: list[int] | set[int] | None = None,
) -> None:
    """Register slash menus. Groups omit reset_paper; private keeps full menu.

    Telegram clients often cache the default/group-wide menu. We also set
    BotCommandScopeChat for each known group id so that chat's shortcut list
    refreshes explicitly.
    """
    groups = [int(x) for x in (group_chat_ids or [])]
    privates = [int(x) for x in (control_chat_ids or [])]

    # Clear then set default + private scopes (full menu).
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
    await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    for chat_id in privates:
        scope = BotCommandScopeChat(chat_id=chat_id)
        await bot.delete_my_commands(scope=scope)
        await bot.set_my_commands(BOT_COMMANDS, scope=scope)

    # Group-wide + each configured group chat (no reset_paper).
    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(BOT_COMMANDS_GROUP, scope=BotCommandScopeAllGroupChats())
    for chat_id in groups:
        scope = BotCommandScopeChat(chat_id=chat_id)
        await bot.delete_my_commands(scope=scope)
        await bot.set_my_commands(BOT_COMMANDS_GROUP, scope=scope)

    logger.info(
        "telegram bot commands registered private=%s group=%s scoped_groups=%s scoped_private=%s",
        [c.command for c in BOT_COMMANDS],
        [c.command for c in BOT_COMMANDS_GROUP],
        groups,
        privates,
    )


def build_dispatcher(
    *,
    control_chat_ids: set[int],
    group_chat_ids: set[int] | None = None,
    db: Database,
    client: GmgnClient,
    app_cfg: AppConfig,
    enabled_chains: list[str],
    narrative: NarrativeService | None = None,
    # Backward-compatible alias used by older callers/tests.
    allowed_chat_ids: set[int] | None = None,
) -> Dispatcher:
    control = set(control_chat_ids)
    if allowed_chat_ids is not None and not control:
        control = set(allowed_chat_ids)
    groups = set(group_chat_ids or ())
    allowed = control | groups

    dp = Dispatcher()
    router = Router()

    def _chat_id(message: Message) -> int | None:
        return message.chat.id if message.chat else None

    def _authorized(message: Message) -> bool:
        chat_id = _chat_id(message)
        if chat_id is None or chat_id not in allowed:
            logger.warning("ignored message from unauthorized chat_id=%s", chat_id)
            return False
        return True

    def _can_reset(message: Message) -> bool:
        chat_id = _chat_id(message)
        return chat_id is not None and chat_id in control

    @router.message(Command("chatid"))
    async def cmd_chatid(message: Message) -> None:
        # Public on purpose: used to discover group ids after adding the bot.
        chat = message.chat
        if chat is None:
            return
        await message.answer(
            f"chat_id={chat.id}\ntype={chat.type}",
            parse_mode=None,
        )

    async def _report_chains() -> list[str]:
        """Enabled chains plus any disabled chain that still has paper activity."""
        names = list(enabled_chains)
        seen = set(names)
        for name in app_cfg.chains:
            if name in seen:
                continue
            summary = await db.paper_stats_summary(name)
            if any(
                int(summary.get(k) or 0) > 0
                for k in (
                    "open_count",
                    "closed_count",
                    "opened_count",
                    "skipped_open_count",
                )
            ):
                names.append(name)
                seen.add(name)
        return names

    def _help_text(message: Message) -> str:
        return render_help(
            app_cfg,
            enabled_chains=enabled_chains,
            include_reset=_can_reset(message),
        )

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        if not _authorized(message):
            return
        await message.answer(_help_text(message), parse_mode="HTML")

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        if not _authorized(message):
            return
        await message.answer(_help_text(message), parse_mode="HTML")

    @router.message(Command("positions"))
    async def cmd_positions(message: Message) -> None:
        if not _authorized(message):
            return
        rows = await db.list_open_papers()
        quotes: dict[tuple[str, str], dict[str, float | None]] = {}
        for row in rows:
            key = (row["chain"], row["token"])
            try:
                price, market_cap = await client.get_price_and_market_cap(
                    row["chain"], row["token"], app_cfg.global_.price_source
                )
                quotes[key] = {"price": price, "market_cap": market_cap}
            except Exception:  # noqa: BLE001
                logger.exception("quote for position failed")
                quotes[key] = {"price": None, "market_cap": None}
        await message.answer(render_positions(rows, quotes=quotes), parse_mode="HTML")

    @router.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        if not _authorized(message):
            return
        chains = await _report_chains()
        per_chain: dict[str, tuple[dict, list]] = {}
        for name in chains:
            summary = await db.paper_stats_summary(name)
            closed = await db.list_recent_closed_papers(5, chain=name)
            per_chain[name] = (summary, closed)
        await message.answer(render_stats(per_chain=per_chain), parse_mode="HTML")

    @router.message(Command("rejects"))
    async def cmd_rejects(message: Message) -> None:
        if not _authorized(message):
            return
        rows = await db.top_reject_reasons(15)
        await message.answer(render_rejects(rows), parse_mode="HTML")

    @router.message(Command("alerts"))
    async def cmd_alerts(message: Message) -> None:
        if not _authorized(message):
            return
        chains = await _report_chains()
        per_chain: dict[str, list] = {}
        for name in chains:
            per_chain[name] = await db.list_recent_alerts(
                app_cfg.global_.alerts_per_chain, chain=name
            )
        await message.answer(render_alerts(per_chain=per_chain), parse_mode="HTML")

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _authorized(message):
            return
        chain_rows: list[dict] = []
        for name in enabled_chains:
            chain_cfg = app_cfg.chains.get(name)
            mode = chain_cfg.execution.mode if chain_cfg else "paper"
            summary = await db.paper_stats_summary(name)
            cool = await db.count_active_cooldowns(name)
            chain_rows.append(
                {
                    "name": name,
                    "mode": mode,
                    "open_count": int(summary.get("open_count") or 0),
                    "cooldowns": cool,
                }
            )
        await message.answer(render_status(chain_rows=chain_rows), parse_mode="HTML")

    @router.message(Command("rounds"))
    async def cmd_rounds(message: Message) -> None:
        if not _authorized(message):
            return
        parts = (message.text or "").split()
        if len(parts) == 2 and parts[1].isdigit():
            round_id = int(parts[1])
            detail: list[dict] = []
            for name in app_cfg.chains:
                summ = await db.archive_round_stats(round_id, chain=name)
                if summ["closed_count"] or summ["open_count"]:
                    detail.append(summ)
            if not detail:
                await message.answer(
                    f"📦 round #{round_id} 无数据（用 /rounds 查看可用的轮次）。",
                    parse_mode="HTML",
                )
                return
            all_summ = await db.archive_round_stats(round_id, chain=None)
            recent = await db.list_archive_closed_papers(round_id, limit=5)
            await message.answer(
                render_rounds([], detail=[all_summ, *detail], recent_closed=recent),
                parse_mode="HTML",
            )
            return
        rows = await db.list_archive_rounds(20)
        await message.answer(render_rounds(rows), parse_mode="HTML")

    @router.message(Command("reset_paper"))
    async def cmd_reset_paper(message: Message) -> None:
        if not _authorized(message):
            return
        if not _can_reset(message):
            await message.answer(
                "⛔ /reset_paper 仅限私聊控制台使用，群组禁止清空模拟。",
                parse_mode="HTML",
            )
            return
        parts = (message.text or "").split()
        valid_scopes = {"sol", "bsc", "robinhood", "all"}
        # BREAKING: scope (chain|all) is now required. Bare `/reset_paper confirm`
        # (no scope) no longer deletes anything — it just re-shows the hint.
        if len(parts) != 3 or parts[1].lower() not in valid_scopes or parts[2].lower() != "confirm":
            await message.answer(render_reset_paper_hint(), parse_mode="HTML")
            return
        chain = parts[1].lower()
        deleted = await db.reset_paper_experiment(chain)
        logger.info(
            "paper experiment reset chain=%s by chat_id=%s deleted=%s",
            chain,
            message.chat.id,
            deleted,
        )
        await message.answer(render_reset_paper(deleted, chain=chain), parse_mode="HTML")

    _query_throttle: dict[int, float] = {}

    @router.message(F.text)
    async def fallback(message: Message) -> None:
        if not _authorized(message):
            return
        handled = await _handle_ca_message(
            chat_id=_chat_id(message) or 0,
            text=message.text or "",
            client=client,
            app_cfg=app_cfg,
            throttle=_query_throttle,
            reply=message.reply,
            narrative=narrative,
        )
        if handled:
            return
        await message.answer(render_unknown_command(), parse_mode="HTML")

    dp.include_router(router)
    return dp
