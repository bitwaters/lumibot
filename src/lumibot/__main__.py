from __future__ import annotations

import asyncio
import logging
import signal
import sys

from lumibot.config import Settings, enabled_chains, load_app_config
from lumibot.news import NewsPoller, OpenNewsClient
from lumibot.db import Database
from lumibot.gmgn.client import GmgnClient, RateLimiter
from lumibot.ipv4 import probe_ipv4_or_raise
from lumibot.pipeline import ChainPipeline
from lumibot.telegram_bot import build_dispatcher, register_bot_commands
from lumibot.telegram_notify import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("lumibot")


async def run() -> None:
    settings = Settings()
    if not settings.gmgn_api_key:
        raise SystemExit("GMGN_API_KEY is required")
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    chat_ids = settings.chat_ids()
    if not chat_ids:
        raise SystemExit("TELEGRAM_CHAT_IDS is required")
    push_chat_ids = settings.push_chat_ids()
    group_chat_ids = settings.group_chat_ids()

    await probe_ipv4_or_raise(skip=settings.lumibot_skip_ipv4_check)

    app_cfg = load_app_config(settings.lumibot_config)
    chains = enabled_chains(app_cfg)
    if not chains:
        raise SystemExit("no enabled chains in config")

    db = Database(settings.lumibot_db_path)
    await db.connect()
    slip_by_chain = {
        name: float(cfg.execution.slippage_buy_pct) for name, cfg in app_cfg.chains.items()
    }
    n_backfill = await db.backfill_open_mark(slip_by_chain)
    if n_backfill:
        logger.info("backfilled open_mark rows=%s", n_backfill)
    limiter = RateLimiter(
        app_cfg.global_.rate_limit.capacity,
        app_cfg.global_.rate_limit.refill_per_sec,
    )
    client = GmgnClient(
        settings.gmgn_api_key,
        limiter,
        cache_ttl_sec=app_cfg.global_.enrichment_cache_ttl_sec,
        security_cache_ttl_sec=app_cfg.global_.security_cache_ttl_sec,
        min_interval_sec=app_cfg.global_.rate_limit.min_interval_sec,
    )
    news_poller: NewsPoller | None = None
    news_cfg = app_cfg.global_.news
    if news_cfg and news_cfg.enabled:
        if settings.opennews_token:
            news_client = OpenNewsClient(settings.opennews_token)
            news_poller = NewsPoller(news_client, news_cfg)
            await news_poller.start()
            logger.info("opennews poller started")
        else:
            logger.warning("global.news enabled but OPENNEWS_TOKEN is missing; news enrichment disabled")

    notifier = TelegramNotifier(
        settings.telegram_bot_token,
        push_chat_ids,
        # Trade events (stage1/closes) only reach control chats, not groups.
        event_chat_ids=chat_ids,
    )
    logger.info(
        "telegram destinations control=%s push=%s (groups=%s)",
        len(chat_ids),
        len(push_chat_ids),
        len(group_chat_ids),
    )

    pipelines = [
        ChainPipeline(
            name,
            cfg,
            app_cfg,
            client,
            db,
            notifier,
            news_poller=news_poller,
        )
        for name, cfg in chains.items()
    ]
    for p in pipelines:
        p.start()
        logger.info("pipeline started chain=%s", p.chain)

    dp = build_dispatcher(
        control_chat_ids=set(chat_ids),
        group_chat_ids=set(group_chat_ids),
        db=db,
        client=client,
        app_cfg=app_cfg,
        enabled_chains=list(chains.keys()),
    )
    await register_bot_commands(
        notifier.bot,
        group_chat_ids=group_chat_ids,
        control_chat_ids=chat_ids,
    )
    polling_task = asyncio.create_task(dp.start_polling(notifier.bot), name="tg-polling")

    stop = asyncio.Event()

    def _ask_stop(*_args) -> None:
        logger.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _ask_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _ask_stop())

    await stop.wait()
    polling_task.cancel()
    await asyncio.gather(polling_task, return_exceptions=True)
    for p in pipelines:
        await p.stop()
    if news_poller is not None:
        await news_poller.stop()
    await notifier.close()
    await client.aclose()
    await db.close()
    logger.info("shutdown complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
