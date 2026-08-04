from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, Message

from lumibot.config import AppConfig
from lumibot.db import Database
from lumibot.gmgn.client import GmgnClient
from lumibot.telegram_notify import (
    render_alerts,
    render_help,
    render_positions,
    render_rejects,
    render_reset_paper,
    render_reset_paper_hint,
    render_stats,
    render_status,
    render_unknown_command,
)

logger = logging.getLogger(__name__)

BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="开始 / 帮助"),
    BotCommand(command="help", description="查看帮助与模拟规则"),
    BotCommand(command="positions", description="当前模拟持仓"),
    BotCommand(command="stats", description="模拟盈亏统计"),
    BotCommand(command="rejects", description="筛选拦截原因"),
    BotCommand(command="alerts", description="最近告警"),
    BotCommand(command="status", description="运行状态"),
    BotCommand(command="reset_paper", description="清空本轮模拟（需 confirm）"),
]

ALERTS_PER_CHAIN = 5


async def register_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS)
    logger.info("telegram bot commands registered: %s", [c.command for c in BOT_COMMANDS])


def build_dispatcher(
    *,
    allowed_chat_ids: set[int],
    db: Database,
    client: GmgnClient,
    app_cfg: AppConfig,
    enabled_chains: list[str],
) -> Dispatcher:
    dp = Dispatcher()
    router = Router()

    def _authorized(message: Message) -> bool:
        chat_id = message.chat.id if message.chat else None
        if chat_id is None or chat_id not in allowed_chat_ids:
            logger.warning("ignored message from unauthorized chat_id=%s", chat_id)
            return False
        return True

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

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        if not _authorized(message):
            return
        await message.answer(
            render_help(app_cfg, enabled_chains=enabled_chains), parse_mode=None
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        if not _authorized(message):
            return
        await message.answer(
            render_help(app_cfg, enabled_chains=enabled_chains), parse_mode=None
        )

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
        await message.answer(render_positions(rows, quotes=quotes), parse_mode=None)

    @router.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        if not _authorized(message):
            return
        # Per-chain sections: enabled OR any paper activity (disabled chains keep history).
        chains = await _report_chains()
        per_chain: dict[str, tuple[dict, list]] = {}
        for name in chains:
            summary = await db.paper_stats_summary(name)
            closed = await db.list_recent_closed_papers(5, chain=name)
            per_chain[name] = (summary, closed)
        await message.answer(render_stats(per_chain=per_chain), parse_mode=None)

    @router.message(Command("rejects"))
    async def cmd_rejects(message: Message) -> None:
        if not _authorized(message):
            return
        rows = await db.top_reject_reasons(15)
        await message.answer(render_rejects(rows), parse_mode=None)

    @router.message(Command("alerts"))
    async def cmd_alerts(message: Message) -> None:
        if not _authorized(message):
            return
        # Fetch N per chain independently — do not global-LIMIT-then-group
        # (busy SOL must not starve BSC/RH in the card).
        chains = await _report_chains()
        per_chain: dict[str, list] = {}
        for name in chains:
            per_chain[name] = await db.list_recent_alerts(ALERTS_PER_CHAIN, chain=name)
        await message.answer(render_alerts(per_chain=per_chain), parse_mode=None)

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
        await message.answer(render_status(chain_rows=chain_rows), parse_mode=None)

    @router.message(Command("reset_paper"))
    async def cmd_reset_paper(message: Message) -> None:
        if not _authorized(message):
            return
        parts = (message.text or "").split()
        valid_scopes = {"sol", "bsc", "robinhood", "all"}
        # BREAKING: scope (chain|all) is now required. Bare `/reset_paper confirm`
        # (no scope) no longer deletes anything — it just re-shows the hint.
        if len(parts) != 3 or parts[1].lower() not in valid_scopes or parts[2].lower() != "confirm":
            await message.answer(render_reset_paper_hint(), parse_mode=None)
            return
        chain = parts[1].lower()
        deleted = await db.reset_paper_experiment(chain)
        logger.info(
            "paper experiment reset chain=%s by chat_id=%s deleted=%s", chain, message.chat.id, deleted
        )
        await message.answer(render_reset_paper(deleted, chain=chain), parse_mode=None)

    @router.message(F.text)
    async def fallback(message: Message) -> None:
        if not _authorized(message):
            return
        await message.answer(render_unknown_command(), parse_mode=None)

    dp.include_router(router)
    return dp
