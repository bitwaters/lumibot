import time

from lumibot.config import load_app_config
from lumibot.exec_types import ExecResult, PaperTradeEvent
from lumibot.models import NormalizedSafety, Source, TokenCandidate
from lumibot.telegram_bot import BOT_COMMANDS
from lumibot.telegram_notify import (
    gmgn_keyboard,
    gmgn_link,
    reject_reason_label,
    reject_source_label,
    render_card,
    render_help,
    render_paper_event,
    render_positions,
    render_rejects,
    render_reset_paper_hint,
    render_stats,
)


def test_signal_push_card_layout():
    cand = TokenCandidate(
        chain="sol",
        address="SoLAddr123FullContractAddress",
        source=Source.SIGNAL,
        signal_type=12,
        symbol="PEPE",
        name="ignored-for-title",
        price=0.00123,
        trigger_mc=100_000,
        market_cap=125_000,
        liquidity=18_000,
        top10_rate=0.22,
        holder_count=320,
        visiting_count=210,
        open_timestamp=time.time() - 12 * 60,
        safety=NormalizedSafety(
            renounced_mint=True,
            renounced_freeze=True,
            warnings=["creator_hold"],
            rug_ratio=0.05,
            bundler_rate=0.12,
        ),
    )
    paper = ExecResult(status="opened", notional_usd=20, open_mark=0.00123)
    text = render_card(cand, paper=paper, latency_sec=1.8)
    assert text.startswith("📡 [SOL] 信号推送  $PEPE")
    assert "SoLAddr123FullContractAddress" in text
    assert "🕐 开盘" in text
    assert "💰 市值 $125.0K → 触发 $100.0K" in text
    assert "💧 流动性 $18.0K  ·  👥 320" in text
    assert "📊 Top10 22.0%  ·  🔥 210" in text
    assert "🛡 安全 通过" in text
    assert "⏱ 延迟 1.8s" in text
    assert "✅ 已开仓 $20.00" in text
    assert "类型12" not in text
    assert "聪明钱" not in text
    assert "开仓标记" not in text
    assert "命令 /positions" not in text
    assert "策略 名义" not in text
    kb = gmgn_keyboard("sol", "SoLAddr123FullContractAddress")
    assert kb.inline_keyboard[0][0].url == gmgn_link("sol", "SoLAddr123FullContractAddress")


def test_skipped_open_brief():
    cand = TokenCandidate(
        chain="sol",
        address="Addr",
        source=Source.TRENDING,
        symbol="X",
        market_cap=50_000,
        liquidity=10_000,
        top10_rate=0.1,
        holder_count=100,
        visiting_count=80,
    )
    text = render_card(cand, paper=ExecResult(status="skipped_open"), latency_sec=0.5)
    assert "📡 [SOL] 信号推送" in text
    assert "⏭ 未新开（已有仓）" in text
    assert "热门趋势" not in text


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
            entry_mc=100_000,
            exit_mc=80_000,
            hold_sec=192,
        )
    )
    assert "📉 [SOL] 硬止损  $ABC  -$2.50" in text
    assert "Tok123" in text
    assert "入场 $100.0K → 平仓 $80.0K" in text


def test_paper_stage1_event_uses_mc():
    text = render_paper_event(
        PaperTradeEvent(
            kind="stage1",
            chain="sol",
            token="TokStage",
            symbol="STG",
            reason="stage1",
            mark=1.3,
            fill_price=1.235,
            qty=10,
            pnl=2.0,
            notional_usd=20,
            entry_price=1.05,
            remaining_qty=10,
            entry_mc=100_000,
            exit_mc=130_000,
        )
    )
    assert "✂️ [SOL] 回本减仓  $STG" in text
    assert "TokStage" in text
    assert "入场 $100.0K → 减仓 $130.0K" in text
    assert "回收约" in text
    assert "📌 成本已上移" in text


def test_help_and_positions_cards():
    from lumibot.telegram_notify import _pct

    app = load_app_config("config/chains.yaml")
    help_text = render_help(app, enabled_chains=["sol"])
    sol_strategy = app.chains["sol"].strategy
    assert "/stats" in help_text
    assert "/reset_paper" in help_text
    assert "过门后重拉" in help_text or "过门后重取" in help_text
    assert "⏱ 延迟" in help_text
    assert _pct(sol_strategy.hard_stop_pct) in help_text
    assert _pct(sol_strategy.stage1_tp_pct) in help_text
    assert _pct(sol_strategy.trail_drawdown_pct) in help_text
    assert "📋 持仓 0 笔" in render_positions([])
    summary = {
        "open_count": 1,
        "closed_count": 2,
        "closed_pnl": 1.5,
        "open_notional": 20.0,
        "opened_count": 5,
        "skipped_open_count": 2,
        "hard_stop_count": 1,
    }
    text = render_stats(summary, [])
    assert "📊 模拟统计" in text
    assert "[SOL]" in text
    assert "本轮开仓 5  ·  跳过开仓 2" in text
    assert "硬止损 1/2" in text
    assert "close_reason=hard_stop" in text
    assert "/reset_paper <sol|bsc|robinhood|all> confirm" in text
    assert "相对买入成本" in help_text or "含买滑点" in help_text
    hint = render_reset_paper_hint()
    assert "/reset_paper sol confirm" in hint
    assert "将清空" in hint


def test_stats_status_alerts_are_per_chain():
    from lumibot.telegram_notify import render_alerts, render_status

    sol_sum = {
        "open_count": 2,
        "closed_count": 1,
        "closed_pnl": 1.0,
        "open_notional": 40.0,
        "opened_count": 3,
        "skipped_open_count": 0,
        "hard_stop_count": 0,
        "win_count": 1,
    }
    bsc_sum = {
        "open_count": 0,
        "closed_count": 0,
        "closed_pnl": 0.0,
        "open_notional": 0.0,
        "opened_count": 0,
        "skipped_open_count": 1,
        "hard_stop_count": 0,
        "win_count": 0,
    }
    text = render_stats(
        per_chain={
            "sol": (sol_sum, []),
            "bsc": (bsc_sum, []),
        }
    )
    assert "[SOL]" in text and "[BSC]" in text
    assert "本轮开仓 3" in text
    assert "跳过开仓 1" in text
    # No blended primary totals line like "持仓 2" at the top without a chain tag
    assert text.splitlines()[0] == "📊 模拟统计"

    status = render_status(
        chain_rows=[
            {"name": "sol", "mode": "paper", "open_count": 2, "cooldowns": 1},
            {"name": "bsc", "mode": "paper", "open_count": 0, "cooldowns": 0},
        ]
    )
    assert "[SOL] paper  ·  持仓 2  ·  冷却 1" in status
    assert "[BSC] paper  ·  持仓 0  ·  冷却 0" in status

    # Busy SOL must not hide BSC when alerts are fetched per chain
    alerts = render_alerts(
        per_chain={
            "sol": [
                {
                    "chain": "sol",
                    "token": "SolTok",
                    "created_at": 1_700_000_000,
                    "payload_json": '{"symbol":"S","exec_status":"opened"}',
                }
            ]
            * 5,
            "bsc": [
                {
                    "chain": "bsc",
                    "token": "BscTok",
                    "created_at": 1_700_000_100,
                    "payload_json": '{"symbol":"B","dual_source":true}',
                }
            ],
        }
    )
    assert "[SOL]" in alerts and "[BSC]" in alerts
    assert "BscTok" in alerts
    assert "双源" in alerts


def test_positions_grouped_by_chain():
    rows = [
        {
            "chain": "sol",
            "token": "SolA",
            "symbol": "A",
            "entry_price": 1.0,
            "open_mark": 1.0,
            "peak_price": 1.0,
            "cost_basis": 1.0,
            "qty": 10.0,
            "notional_usd": 10.0,
            "stage1_done": 0,
        },
        {
            "chain": "bsc",
            "token": "BscB",
            "symbol": "B",
            "entry_price": 1.0,
            "open_mark": 1.0,
            "peak_price": 1.0,
            "cost_basis": 1.0,
            "qty": 10.0,
            "notional_usd": 20.0,
            "stage1_done": 0,
        },
    ]
    text = render_positions(rows, quotes={})
    assert "[SOL]" in text and "[BSC]" in text
    assert "SolA" in text and "BscB" in text


def test_positions_use_market_cap_not_price():
    row = {
        "chain": "sol",
        "token": "TokABCFullContract",
        "symbol": "ABC",
        "entry_price": 1.05,
        "open_mark": 1.0,
        "peak_price": 1.5,
        "cost_basis": 1.0,
        "qty": 20.0,
        "notional_usd": 20.0,
        "stage1_done": 0,
    }
    text = render_positions(
        [row],
        quotes={("sol", "TokABCFullContract"): {"price": 1.2, "market_cap": 120_000}},
    )
    assert "TokABCFullContract" in text
    assert "入场 $100.0K → 现 $120.0K" in text
    assert "峰 $150.0K" in text


def test_positions_price_fallback_when_mc_missing():
    row = {
        "chain": "sol",
        "token": "TokNoMc",
        "symbol": "NMC",
        "entry_price": 1.05,
        "open_mark": 1.0,
        "peak_price": 1.5,
        "cost_basis": 1.0,
        "qty": 20.0,
        "notional_usd": 20.0,
        "stage1_done": 0,
    }
    text = render_positions(
        [row],
        quotes={("sol", "TokNoMc"): {"price": 1.2, "market_cap": None}},
    )
    assert "入场 1 → 现 1.2" in text
    assert "峰 1.5" in text
    assert "TokNoMc" in text


def test_reject_labels():
    assert reject_reason_label("mc") == "市值"
    assert reject_reason_label("loss_cooldown") == "亏损冷却"
    assert reject_reason_label("too_new") == "过新"
    assert reject_reason_label("liq_ratio") == "流动性占比"

    assert reject_reason_label("no_price") == "无有效价格"
    assert reject_source_label("signal") == "信号"
    text = render_rejects(
        [{"chain": "sol", "source": "signal", "reason": "mc", "count": 3}]
    )
    assert "信号 / 市值 × 3" in text


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
        "reset_paper",
    ]
    assert all(c.description for c in BOT_COMMANDS)
