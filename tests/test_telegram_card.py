from lumibot.exec_types import ExecResult, PaperTradeEvent
from lumibot.models import NormalizedSafety, Source, TokenCandidate
from lumibot.telegram_bot import BOT_COMMANDS
from lumibot.telegram_notify import (
    gmgn_keyboard,
    gmgn_link,
    render_card,
    render_help,
    render_paper_event,
    render_positions,
    render_stats,
)


def test_card_memebot_chinese_layout():
    cand = TokenCandidate(
        chain="sol",
        address="SoLAddr123",
        source=Source.SIGNAL,
        signal_type=12,
        symbol="A&B <C>",
        name="foo>bar",
        price=0.00123,
        trigger_mc=100_000,
        market_cap=125_000,
        liquidity=18_000,
        top10_rate=0.22,
        holder_count=320,
        visiting_count=210,
        safety=NormalizedSafety(
            renounced_mint=True,
            renounced_freeze=True,
            warnings=["creator_hold"],
            rug_ratio=0.05,
            bundler_rate=0.12,
        ),
    )
    paper = ExecResult(
        status="opened",
        entry_price=1.05,
        notional_usd=20,
        buy_slip=0.05,
    )
    text = render_card(cand, paper=paper)
    assert text.startswith("[SOL] 聪明钱 · 类型12")
    assert "$A&B <C>（foo>bar）" in text
    assert "SoLAddr123" in text
    assert "价格 0.00123" in text
    assert "触发市值 $100.0K" in text
    assert "市值 $125.0K" in text
    assert "流动性 $18.0K" in text
    assert "持有人 320" in text
    assert "热度 210" in text
    assert "Top10 22.0%" in text
    assert "✅Mint放弃" in text
    assert "✅冻结放弃" in text
    assert "⚠开发者持仓" in text
    assert "风险 Rug 5.0%" in text
    assert "策略 名义$20" in text
    assert "模拟 ✅开仓 $20.00" in text
    assert "/positions" in text
    assert "GMGN https://" not in text
    kb = gmgn_keyboard("sol", "SoLAddr123")
    assert kb.inline_keyboard[0][0].url == gmgn_link("sol", "SoLAddr123")
    assert kb.inline_keyboard[0][0].text == "打开 GMGN"


def test_paper_close_event_card():
    text = render_paper_event(
        PaperTradeEvent(
            kind="close",
            chain="sol",
            token="Tok123",
            symbol="ABC",
            reason="hard_stop",
            mark=0.8,
            fill_price=0.76,
            qty=20,
            pnl=-2.5,
            notional_usd=20,
            entry_price=1.0,
        )
    )
    assert "[SOL] 模拟 · 硬止损" in text
    assert "盈亏 -$2.50" in text


def test_trending_card_label():
    cand = TokenCandidate(
        chain="bsc",
        address="0xabc",
        source=Source.TRENDING,
        symbol="XYZ",
        market_cap=50_000,
        liquidity=10_000,
        top10_rate=0.1,
        holder_count=100,
        visiting_count=80,
        safety=NormalizedSafety(
            honeypot=False,
            renounced=True,
            open_source=True,
            buy_tax=0.03,
            sell_tax=0.03,
        ),
    )
    text = render_card(cand)
    assert text.startswith("[BSC] 热门趋势")
    assert "$XYZ" in text
    assert "0xabc" in text
    assert "✅非蜜罐" in text
    assert "✅弃权" in text
    assert "✅开源" in text


def test_help_and_positions_cards():
    assert "/stats" in render_help()
    assert "当前无模拟持仓" in render_positions([])
    summary = {
        "open_count": 1,
        "closed_count": 2,
        "closed_pnl": 1.5,
        "open_notional": 20.0,
    }
    text = render_stats(summary, [])
    assert "持仓中：1 笔" in text
    assert "已实现 +$1.50" in text


def test_positions_use_market_cap_not_price():
    row = {
        "chain": "sol",
        "token": "TokABC",
        "symbol": "ABC",
        "entry_price": 1.0,
        "peak_price": 1.5,
        "cost_basis": 1.0,
        "qty": 20.0,
        "notional_usd": 20.0,
        "stage1_done": 0,
    }
    text = render_positions(
        [row],
        quotes={("sol", "TokABC"): {"price": 1.2, "market_cap": 120_000}},
    )
    assert "入场市值 $100.0K" in text
    assert "当前 $120.0K" in text
    assert "峰值 $150.0K" in text
    assert "涨跌 20.0%" in text
    assert "入场 1.0" not in text
    assert "峰值 1.5" not in text


def test_bot_quick_commands():
    names = [c.command for c in BOT_COMMANDS]
    assert names == [
        "start",
        "help",
        "positions",
        "stats",
        "rejects",
        "alerts",
        "status",
    ]
    assert all(c.description for c in BOT_COMMANDS)
