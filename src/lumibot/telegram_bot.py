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
        summary = await db.paper_stats_summary()
        closed = await db.list_recent_closed_papers(8)
        await message.answer(render_stats(summary, closed), parse_mode=None)

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
        rows = await db.list_recent_alerts(10)
        await message.answer(render_alerts(rows), parse_mode=None)

    @router.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if not _authorized(message):
            return
        summary = await db.paper_stats_summary()
        cooldowns = await db.count_active_cooldowns()
        # Collect mode per chain so /status is accurate with multiple chains enabled
        chain_modes: dict[str, str] = {}
        for name in enabled_chains:
            chain_cfg = app_cfg.chains.get(name)
            if chain_cfg:
                chain_modes[name] = chain_cfg.execution.mode
        await message.answer(
            render_status(
                enabled_chains=enabled_chains,
                open_count=int(summary.get("open_count") or 0),
                cooldowns=cooldowns,
                chain_modes=chain_modes,
            ),
            parse_mode=None,
        )

    @router.message(Command("reset_paper"))
    async def cmd_reset_paper(message: Message) -> None:
        if not _authorized(message):
            return
        parts = (message.text or "").split()
        if len(parts) < 2 or parts[1].lower() != "confirm":
            await message.answer(render_reset_paper_hint(), parse_mode=None)
            return
        deleted = await db.reset_paper_experiment()
        logger.info("paper experiment reset by chat_id=%s deleted=%s", message.chat.id, deleted)
        await message.answer(render_reset_paper(deleted), parse_mode=None)

    @router.message(F.text)
    async def fallback(message: Message) -> None:
        if not _authorized(message):
            return
        await message.answer(render_unknown_command(), parse_mode=None)

    dp.include_router(router)
    return dp
