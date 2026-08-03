import time

from lumibot.strategy import Action, StrategyOrder


def _order(mark=1.0, buy_slip=0.05, sell_slip=0.05) -> StrategyOrder:
    return StrategyOrder.open_from_mark(
        chain="sol",
        token="T",
        mark=mark,
        notional_usd=20,
        buy_slip=buy_slip,
        sell_slip=sell_slip,
        opened_at=time.time(),
    )


def test_hard_stop_vs_open_mark():
    o = _order(mark=1.0, buy_slip=0.0)
    # open_mark=1.0; hard stop at 0.5 (−50%)
    action, reason, qty = o.evaluate(0.5, time.time())
    assert action == Action.CLOSE and reason == "hard_stop" and qty == o.qty


def test_hard_stop_ignores_buy_slip_entry():
    """−40% from open_mark must NOT stop when buy slip made entry 5% higher."""
    o = _order(mark=1.0, buy_slip=0.05)
    assert abs(o.entry_price - 1.05) < 1e-12
    assert o.open_mark == 1.0
    action, reason, _ = o.evaluate(0.60, time.time())
    assert action == Action.HOLD and reason is None
    action, reason, _ = o.evaluate(0.50, time.time())
    assert action == Action.CLOSE and reason == "hard_stop"


def test_stage1_recovers_notional_after_sell_slip():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.05)
    # cost_basis=1.0; stage1 when mark >= 1.30
    mark = 1.30
    action, reason, qty = o.evaluate(mark, time.time())
    assert action == Action.STAGE1_SELL
    sell_px = StrategyOrder.sell_fill_price(mark, 0.05)
    assert qty * sell_px >= 20 - 1e-9
    pnl = o.apply_stage1(mark, qty)
    assert o.stage1_done
    assert o.qty > 0
    assert o.cost_basis == sell_px
    assert pnl != 0


def test_hard_stop_ignores_raised_cost_basis():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.stage1_done = True
    o.cost_basis = 2.0
    o.qty = 5
    action, reason, _ = o.evaluate(0.5, time.time())
    assert action == Action.CLOSE and reason == "hard_stop"


def test_trail_not_before_stage1():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.note_mark(1.25)
    # 50% off peak would be trail after stage1; before stage1 must hold
    action, reason, _ = o.evaluate(0.625, time.time())
    assert action == Action.HOLD
    assert reason is None


def test_trail_after_stage1():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.stage1_done = True
    o.qty = 5
    o.peak_price = 2.0
    action, reason, _ = o.evaluate(1.0, time.time())  # 50% off peak
    assert action == Action.CLOSE and reason == "trail"
