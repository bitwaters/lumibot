import time
from html.parser import HTMLParser

from lumibot.config import load_app_config
from lumibot.exec_types import ExecResult, PaperTradeEvent
from lumibot.models import NormalizedSafety, Source, TokenCandidate
from lumibot.telegram_bot import BOT_COMMANDS, BOT_COMMANDS_GROUP
from lumibot.telegram_notify import (
    append_news_line,
    dexscreener_link,
    gmgn_keyboard,
    gmgn_link,
    reject_reason_label,
    reject_source_label,
    render_alerts,
    render_card,
    render_help,
    render_paper_event,
    render_positions,
    render_rejects,
    render_reset_paper,
    render_reset_paper_hint,
    render_rounds,
    render_stats,
    render_status,
    render_unknown_command,
)


_ALLOWED_TAGS = {"b", "code", "a"}


class _HtmlCheck(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag not in _ALLOWED_TAGS:
            self.errors.append(f"unexpected tag <{tag}>")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"mismatched </{tag}>")
        else:
            self.stack.pop()


def _assert_html_ok(text: str) -> None:
    checker = _HtmlCheck()
    checker.feed(text)
    assert checker.errors == [], checker.errors
    assert checker.stack == [], checker.stack


def _cand(**kw) -> TokenCandidate:
    base = dict(
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
        volume_1h=8_100,
        platform="pump.fun",
        open_timestamp=time.time() - 12 * 60,
        safety=NormalizedSafety(
            renounced_mint=True,
            renounced_freeze=True,
            warnings=["creator_hold"],
            rug_ratio=0.05,
            bundler_rate=0.12,
            buy_tax=0.05,
            sell_tax=0.05,
        ),
    )
    base.update(kw)
    return TokenCandidate(**base)


def test_signal_push_card_layout():
    cand = _cand()
    paper = ExecResult(status="opened", notional_usd=20, open_mark=0.00123)
    text = render_card(cand, paper=paper, latency_sec=1.8)
    assert text.startswith("📡 <b>$PEPE</b> · SOL")
    assert "<b>📊 指标</b>" in text
    assert "📍 CA: <code>SoLAddr123FullContractAddress</code>" in text
    assert "<code>💰 市值    $125.0K → 触发 $100.0K (25.0%)</code>" in text
    assert "<code>⏱ 开盘     12m       💧 流动性  $18.0K</code>" in text
    assert "<code>👥 持有人  320       👑 Top10   22.0%</code>" in text
    assert "<code>🔥 热度    210       🚀 1H 成交 $8.1K</code>" in text
    assert "<code>🏭 平台    pump.fun</code>" in text
    assert "买税 5.0% · 卖税 5.0%" in text
    assert "⚠ 开发者持仓" in text
    assert "<b>✅ 已开仓 $20.00</b> · ⏱ 延迟 1.8s" in text
    assert "类型12" not in text
    assert "聪明钱" not in text
    assert "开仓标记" not in text
    assert "命令 /positions" not in text
    assert "策略 名义" not in text
    kb = gmgn_keyboard("sol", "SoLAddr123FullContractAddress")
    assert [b.text for b in kb.inline_keyboard[0]] == ["打开 GMGN", "DexScreener"]
    assert kb.inline_keyboard[0][0].url == gmgn_link("sol", "SoLAddr123FullContractAddress")
    assert kb.inline_keyboard[0][1].url == dexscreener_link("sol", "SoLAddr123FullContractAddress")


def test_signal_card_dual_source_badge():
    text = render_card(_cand(dual_source=True), paper_status="opening")
    assert "📡 <b>$PEPE</b> · SOL · 双源" in text
    assert "<b>⏳ 开仓中</b> · ⏱ 延迟 —" in text


def test_signal_card_trending_without_trigger():
    cand = _cand(source=Source.TRENDING, trigger_mc=None)
    text = render_card(cand, paper_status="opening")
    assert "<code>💰 市值    $125.0K</code>" in text
    assert "→ 触发" not in text
    assert "📡 <b>$PEPE</b> · SOL" in text


def test_signal_card_missing_metrics_dash():
    cand = _cand(
        market_cap=None,
        trigger_mc=None,
        liquidity=None,
        top10_rate=None,
        holder_count=None,
        visiting_count=None,
        volume_1h=None,
        platform=None,
        open_timestamp=None,
    )
    text = render_card(cand, paper_status="opening", latency_sec=None)
    assert "<code>💰 市值    —</code>" in text
    assert "💧 流动性  —" in text
    assert "👑 Top10   —" in text
    assert "🚀 1H 成交 —" in text
    assert "🏭 平台" not in text


def test_signal_card_tax_hidden_when_zero():
    safety = NormalizedSafety()
    text = render_card(_cand(safety=safety), paper_status="opening")
    assert "🛡 安全 通过" in text
    assert "买税" not in text
    assert "卖税" not in text


def test_signal_card_escapes_external_data():
    cand = _cand(symbol="PEPE<3", address="addr<&>")
    text = render_card(cand, paper_status="opening")
    assert "PEPE&lt;3" in text
    assert "addr&lt;&amp;&gt;" in text
    assert "<b>PEPE<3</b>" not in text


def test_status_line_states():
    cand = _cand()
    cases = [
        (ExecResult(status="skipped_open"), "⏭ 未新开（已有仓）"),
        (ExecResult(status="blocked_max_positions"), "⛔ 未新开（已达持仓上限）"),
        (ExecResult(status="no_price"), "⛔ 未开仓（无价格）"),
        (ExecResult(status="blocked_live"), "⛔ 实盘已阻断"),
    ]
    for paper, marker in cases:
        text = render_card(cand, paper=paper, latency_sec=0.5)
        assert f"<b>{marker}</b> · ⏱ 延迟 0.5s" in text
    text = render_card(cand, paper_status="precheck_skipped_open")
    assert "<b>↪️ 未新开</b>" in text
    text = render_card(cand, paper_status="executor_error")
    assert "<b>⛔ 执行异常</b>" in text


def test_append_news_line_freeze_insert():
    cand = _cand()
    base = render_card(cand, paper=ExecResult(status="opened", notional_usd=20, open_mark=0.00123), latency_sec=1.8)
    news_line = "📰 相关 token-specific update"
    enriched = append_news_line(base, news_line)
    assert enriched.startswith(base.rstrip("\n"))
    assert enriched.splitlines()[-1] == news_line
    assert sum(1 for line in enriched.splitlines() if line.startswith("📰")) == 1
    for key in ("💰 市值", "💧 流动性", "⏱ 延迟", "✅ 已开仓"):
        assert key in enriched


def test_append_news_line_replaces_existing_news_line():
    base = render_card(_cand(), paper_status="opening")
    first = append_news_line(base, "📰 相关 first hit")
    second = append_news_line(first, "📰 市场 market-wide update")
    lines = second.splitlines()
    assert sum(1 for line in lines if line.startswith("📰")) == 1
    assert lines[-1] == "📰 市场 market-wide update"


def test_append_news_line_escapes_external_content():
    base = render_card(_cand(), paper_status="opening")
    enriched = append_news_line(base, "📰 <b>bold</b> & <script>")
    assert enriched.splitlines()[-1] == "📰 &lt;b&gt;bold&lt;/b&gt; &amp; &lt;script&gt;"


def test_append_news_line_none_returns_original():
    base = render_card(_cand(), paper_status="opening")
    assert append_news_line(base, None) == base
    assert append_news_line(base, "") == base


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
    assert "📉 <b>$ABC</b> · SOL · 硬止损  <b>-$2.50</b>" in text
    assert "📍 CA: <code>Tok123</code>" in text
    assert "💰 入场市值 <b>$100.0K</b> → 平仓市值 <b>$80.0K</b>" in text
    assert "<code>⏱ 持仓     3m        投入       $20.00</code>" in text


def test_paper_close_peak_and_timeout():
    text = render_paper_event(
        PaperTradeEvent(
            kind="close",
            chain="sol",
            token="Tok123",
            symbol="ABC",
            reason="trail",
            mark=1.2,
            fill_price=1.18,
            qty=20,
            pnl=3.6,
            notional_usd=24,
            entry_price=1.0,
            entry_mc=100_000,
            exit_mc=120_000,
            peak_mc=135_000,
            hold_sec=900,
        )
    )
    assert "<code>📈 峰值    $135.0K   ⏱ 持仓     15m</code>" in text
    assert "<code>投入       $24.00</code>" in text


def test_paper_close_price_fallback_labels():
    text = render_paper_event(
        PaperTradeEvent(
            kind="close",
            chain="bsc",
            token="TokBsc",
            symbol="DOGE",
            reason="hard_stop",
            mark=0.8,
            fill_price=0.76,
            qty=25,
            pnl=-5.0,
            notional_usd=25,
            entry_price=1.0,
        )
    )
    assert "<code>标记价     0.8       盈亏       -$5.00</code>" in text
    assert "<code>投入       $25.00    入场价     1</code>" in text


def test_paper_stage1_notional_mode():
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
            sell_mode="notional",
        )
    )
    assert "✂️ <b>$STG</b> · SOL · 回本减仓" in text
    assert "📍 CA: <code>TokStage</code>" in text
    assert "💰 入场市值 <b>$100.0K</b> → 减仓市值 <b>$130.0K</b>" in text
    assert "💰 回收约 <b>$12.35</b> · 剩余仓位继续持有" in text
    assert "📌 已回本 · 剩余仓位零成本" in text


def test_paper_stage1_ratio_mode():
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
            sell_mode="ratio",
        )
    )
    assert "📌 剩余仓位成本按减仓价计算" in text
    assert "已回本 · 剩余仓位零成本" not in text


def test_help_and_positions_cards():
    from lumibot.telegram_notify import _pct

    app = load_app_config("config/chains.yaml")
    help_text = render_help(app, enabled_chains=["sol"])
    sol_strategy = app.chains["sol"].strategy
    assert "/stats" in help_text
    assert "/reset_paper" in help_text
    assert "筛选通过后信号推送" in help_text
    assert "筛选通过后重拉的实时 token 快照" in help_text
    assert "不二次筛选" in help_text
    assert "⏱ 延迟" in help_text
    assert "单仓投入" in help_text
    assert "买入" in help_text and "卖出" in help_text
    assert _pct(sol_strategy.hard_stop_pct) in help_text
    assert f"盈利 {_pct(sol_strategy.stage1_tp_pct)} 触发回本减仓" in help_text
    if sol_strategy.stage1_sell_mode == "ratio":
        assert f"减仓 比例 {_pct(sol_strategy.stage1_sell_ratio)}" in help_text
    else:
        assert "减仓 回收本金" in help_text
    assert f"剩余仓位峰值回撤 {_pct(sol_strategy.trail_drawdown_pct)} 平仓" in help_text
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
    assert "<code>持仓       1         投入       $20.00</code>" in text
    assert "<code>本轮开仓   5         跳过开仓   2</code>" in text
    assert "<code>硬止损     1/2       止损率     50.0%</code>" in text
    assert "close_reason=hard_stop" not in text
    assert "含回本减仓后再次硬止损" in text
    assert "/reset_paper &lt;sol|bsc|robinhood|all&gt; confirm" in text
    hint = render_reset_paper_hint()
    assert "/reset_paper sol confirm" in hint
    assert "将清空" in hint
    assert "快照" not in hint


def test_stats_status_alerts_are_per_chain():
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
    assert "<code>本轮开仓   3         跳过开仓   0</code>" in text
    assert "<code>本轮开仓   0         跳过开仓   1</code>" in text
    assert text.splitlines()[0] == "<b>📊 模拟统计</b>"

    status = render_status(
        chain_rows=[
            {"name": "sol", "mode": "paper", "open_count": 2, "cooldowns": 1},
            {"name": "bsc", "mode": "paper", "open_count": 0, "cooldowns": 0},
        ]
    )
    assert "<b>[SOL]</b> paper  ·  持仓 <b>2</b>  ·  冷却 <b>1</b>" in status
    assert "<b>[BSC]</b> paper  ·  持仓 <b>0</b>  ·  冷却 <b>0</b>" in status

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
    assert "<b>[SOL]</b>" in alerts and "<b>[BSC]</b>" in alerts
    assert "✅开仓" in alerts
    assert "双源" in alerts
    assert "<code>BscTok</code>" in alerts


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
    assert "<b>[SOL]" in text and "<b>[BSC]" in text
    assert "投入 <b>$30.00</b>" in text
    assert "<code>SolA</code>" in text and "<code>BscB</code>" in text


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
    assert "<code>TokABCFullContract</code>" in text
    assert "入场 <b>$100.0K</b> → 现 <b>$120.0K</b>" in text
    assert "峰 <b>$150.0K</b>" in text


def test_positions_price_fallback_labels():
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
    assert "入场价 1 → 现价 1.2" in text
    assert "峰值 1.5" in text
    assert "<code>TokNoMc</code>" in text


def test_reject_labels_and_render():
    assert reject_reason_label("mc") == "市值"
    assert reject_reason_label("loss_cooldown") == "亏损冷却"
    assert reject_reason_label("too_new") == "过新"
    assert reject_reason_label("liq_ratio") == "流动性占比"
    assert reject_reason_label("no_price") == "无有效价格"
    assert reject_source_label("signal") == "信号"
    text = render_rejects(
        [{"chain": "sol", "source": "signal", "reason": "mc", "count": 3}]
    )
    assert "· [sol] 信号 / 市值 × <b>3</b>" in text
    assert "<b>🚫 拦截 Top</b>" in text


def test_rounds_cards():
    text = render_rounds(
        [
            {"round_id": 1786123456, "positions": 18, "closed_count": 15, "open_count": 3, "closed_pnl": 24.5},
        ]
    )
    assert "<b>📦 归档轮次</b>" in text
    assert "round #1786123456   仓位 18   平/在持 15/3   已实现 +$24.50" in text

    text = render_rounds(
        [],
        detail=[
            {"round_id": 1786123456, "chain": None, "closed_count": 15, "open_count": 3, "closed_pnl": 24.5, "win_rate": 0.53, "hard_stop_count": 4, "avg_win_usd": 6.1, "avg_loss_usd": -2.3},
        ],
    )
    assert "round #1786123456 详情" in text
    assert "<code>平/在持    15 / 3    已实现     +$24.50</code>" in text
    assert "<code>胜率       53%       硬止损     4</code>" in text
    assert "<code>均盈       +$6.10    均亏       -$2.30</code>" in text
    assert "均赢" not in text
    assert "$-2.30" not in text

    assert "暂无历史轮次" in render_rounds([])


def test_reset_paper_cards():
    text = render_reset_paper(
        {"paper_positions": 3, "paper_fills": 8, "paper_skip_opens": 2, "cooldowns": 6, "alerts": 12, "reject_counts": 33, "round_id": 123},
        chain="sol",
    )
    assert "🧹 [SOL] 模拟已重置" in text
    assert "<code>持仓       3         成交       8</code>" in text
    assert "仓位行" not in text
    assert "快照" not in text
    assert "round #123" in text


def test_dexscreener_chain_aware():
    kb = gmgn_keyboard("sol", "Addr")
    assert [b.text for b in kb.inline_keyboard[0]] == ["打开 GMGN", "DexScreener"]
    kb = gmgn_keyboard("bsc", "Addr")
    assert [b.text for b in kb.inline_keyboard[0]] == ["打开 GMGN", "DexScreener"]
    kb = gmgn_keyboard("robinhood", "Addr")
    assert [b.text for b in kb.inline_keyboard[0]] == ["打开 GMGN"]
    assert dexscreener_link("robinhood", "Addr") is None
    assert dexscreener_link("sol", "Addr") == "https://dexscreener.com/solana/Addr"


def test_bot_quick_commands():
    names = [c.command for c in BOT_COMMANDS]
    assert names == [
        "positions",
        "stats",
        "alerts",
        "status",
        "rejects",
        "rounds",
        "help",
        "start",
        "chatid",
        "reset_paper",
    ]
    group_names = [c.command for c in BOT_COMMANDS_GROUP]
    assert "reset_paper" not in group_names
    assert group_names == [
        "positions",
        "stats",
        "alerts",
        "status",
        "rejects",
        "rounds",
        "help",
        "start",
        "chatid",
    ]
    assert all(c.description for c in BOT_COMMANDS)
    desc = {c.command: c.description for c in BOT_COMMANDS}
    assert desc["positions"] == "当前模拟持仓"
    assert desc["stats"] == "盈亏统计"
    assert desc["rejects"] == "拦截原因 Top"
    assert desc["rounds"] == "历史轮次"
    assert desc["help"] == "帮助与模拟规则"
    assert desc["reset_paper"] == "清空模拟（需 confirm）"


def test_help_omits_reset_when_requested():
    app = load_app_config("config/chains.yaml")
    with_reset = render_help(app, enabled_chains=["sol"], include_reset=True)
    no_reset = render_help(app, enabled_chains=["sol"], include_reset=False)
    assert "/reset_paper &lt;sol|bsc|robinhood|all&gt; confirm" in with_reset
    assert "仅限私聊控制台" in no_reset
    assert "/reset_paper &lt;sol|bsc|robinhood|all&gt; confirm" not in no_reset
    assert "命令：/positions /stats /alerts /status /rejects /rounds" in no_reset
    assert "/reset_paper" not in no_reset.splitlines()[3]


def test_help_command_order_matches_menu():
    app = load_app_config("config/chains.yaml")
    text = render_help(app, enabled_chains=["sol"], include_reset=True)
    cmd_line = text.splitlines()[3]
    assert cmd_line.startswith("命令：/positions /stats /alerts /status /rejects /rounds /reset_paper /chatid")


def test_all_cards_html_is_well_formed():
    """Every card must be valid HTML for parse_mode=HTML (regression: raw
    <sol|...> in command hints broke /stats /help /rounds replies)."""
    app = load_app_config("config/chains.yaml")
    cand = _cand()
    cand_trending = _cand(source=Source.TRENDING, trigger_mc=None)
    close_ev = PaperTradeEvent(kind="close", chain="sol", token="Tok123", symbol="ABC", reason="hard_stop", mark=0.8, fill_price=0.76, qty=20, pnl=-2.5, notional_usd=20, entry_price=1.0, entry_mc=100_000, exit_mc=80_000, hold_sec=192)
    close_ev_fallback = PaperTradeEvent(kind="close", chain="bsc", token="TokBsc", symbol="DOGE", reason="hard_stop", mark=0.8, fill_price=0.76, qty=25, pnl=-5.0, notional_usd=25, entry_price=1.0)
    stage1_ev = PaperTradeEvent(kind="stage1", chain="sol", token="TokStage", symbol="STG", reason="stage1", mark=1.3, fill_price=1.235, qty=10, pnl=2.0, notional_usd=20, entry_price=1.05, remaining_qty=10, entry_mc=100_000, exit_mc=130_000)
    pos_row = {
        "chain": "sol", "token": "TokABCFullContract", "symbol": "ABC",
        "entry_price": 1.05, "open_mark": 1.0, "peak_price": 1.5,
        "cost_basis": 1.0, "qty": 20.0, "notional_usd": 20.0, "stage1_done": 0,
    }
    summary = {
        "open_count": 2, "closed_count": 3, "closed_pnl": 1.5, "open_notional": 40.0,
        "opened_count": 5, "skipped_open_count": 2, "hard_stop_count": 1,
        "win_count": 2, "avg_win_usd": 2.25, "avg_loss_usd": -1.0, "avg_hold_sec": 2700,
    }
    round_row = {"round_id": 1786123456, "positions": 18, "closed_count": 15, "open_count": 3, "closed_pnl": 24.5}
    round_detail = {"round_id": 1786123456, "chain": None, "closed_count": 15, "open_count": 3, "closed_pnl": 24.5, "win_rate": 0.53, "hard_stop_count": 4, "avg_win_usd": 6.1, "avg_loss_usd": -2.3}

    cards = [
        render_card(cand, paper=ExecResult(status="opened", notional_usd=20), latency_sec=1.8),
        render_card(cand, paper_status="opening", latency_sec=1.8),
        render_card(cand, paper=ExecResult(status="skipped_open"), latency_sec=0.5),
        render_card(cand_trending, paper_status="opening"),
        render_card(_cand(market_cap=None, trigger_mc=None, liquidity=None, top10_rate=None, holder_count=None, visiting_count=None, volume_1h=None, platform=None, open_timestamp=None), paper_status="opening"),
        append_news_line(render_card(cand, paper_status="opening"), "📰 相关 <b>bold</b> & text"),
        render_paper_event(close_ev),
        render_paper_event(close_ev_fallback),
        render_paper_event(stage1_ev),
        render_positions([pos_row], quotes={("sol", "TokABCFullContract"): {"price": 1.2, "market_cap": 120_000}}),
        render_positions([], quotes={}),
        render_stats(per_chain={"sol": (summary, []), "bsc": ({}, [])}),
        render_rejects([{"chain": "sol", "source": "signal", "reason": "mc", "count": 3}]),
        render_status(chain_rows=[{"name": "sol", "mode": "paper", "open_count": 2, "cooldowns": 1}]),
        render_alerts(rows=[{"chain": "sol", "token": "SolTok", "created_at": 1_700_000_000, "payload_json": '{"symbol":"S","exec_status":"opened"}'}]),
        render_rounds([round_row]),
        render_rounds([], detail=[round_detail]),
        render_rounds([]),
        render_reset_paper_hint(),
        render_reset_paper({"paper_positions": 3, "paper_fills": 8, "paper_skip_opens": 2, "cooldowns": 6, "alerts": 12, "reject_counts": 33}, chain="sol"),
        render_help(app, enabled_chains=["sol"], include_reset=True),
        render_help(app, enabled_chains=["sol"], include_reset=False),
        render_unknown_command(),
    ]
    for card in cards:
        _assert_html_ok(card)
