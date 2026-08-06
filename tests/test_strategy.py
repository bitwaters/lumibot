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
    # open_mark=1.0; hard stop at 0.70 (−30%)
    action, reason, qty = o.evaluate(0.70, time.time())
    assert action == Action.CLOSE and reason == "hard_stop" and qty == o.qty


def test_early_stop_tighter_in_protection_window():
    o = StrategyOrder.open_from_mark(
        chain="sol", token="T", mark=1.0, notional_usd=20,
        buy_slip=0.0, sell_slip=0.0, opened_at=time.time(),
        hard_stop_pct=-0.20, early_stop_pct=-0.10, early_stop_sec=120,
    )
    # Inside the window: −15% triggers early_stop (hard_stop would need −20%).
    action, reason, _ = o.evaluate(0.85, time.time())
    assert action == Action.CLOSE and reason == "early_stop"
    # Inside the window but above −10%: hold.
    action, reason, _ = o.evaluate(0.92, time.time())
    assert action == Action.HOLD


def test_early_stop_expires_back_to_hard_stop():
    opened = time.time() - 300  # past the 120s window
    o = StrategyOrder.open_from_mark(
        chain="sol", token="T", mark=1.0, notional_usd=20,
        buy_slip=0.0, sell_slip=0.0, opened_at=opened,
        hard_stop_pct=-0.20, early_stop_pct=-0.10, early_stop_sec=120,
    )
    # After the window −15% is not a stop; only −20% hard stop triggers.
    action, reason, _ = o.evaluate(0.85, time.time())
    assert action == Action.HOLD
    action, reason, _ = o.evaluate(0.79, time.time())
    assert action == Action.CLOSE and reason == "hard_stop"


def _momentum_order(**kw) -> StrategyOrder:
    base = dict(
        chain="sol", token="T", mark=1.0, notional_usd=20,
        buy_slip=0.0, sell_slip=0.0, opened_at=time.time(),
        hard_stop_pct=-0.20, momentum_sec=90,
        momentum_activate_pct=0.02, momentum_exit_pct=-0.05,
    )
    base.update(kw)
    return StrategyOrder.open_from_mark(**base)


def test_no_momentum_exit_in_window():
    o = _momentum_order()
    # Never rose 2% (peak stays 1.0) and price at -5%: exit.
    action, reason, _ = o.evaluate(0.95, time.time())
    assert action == Action.CLOSE and reason == "no_momentum"
    # Above the -5% line inside the window: hold.
    o2 = _momentum_order()
    action, reason, _ = o2.evaluate(0.97, time.time())
    assert action == Action.HOLD


def test_no_momentum_skipped_once_price_rose():
    o = _momentum_order()
    o.note_mark(1.03)  # rose past the 2% activate threshold
    action, reason, _ = o.evaluate(0.95, time.time())
    assert action == Action.HOLD  # early_stop (-15%? no) -> -5% is not a stop yet


def test_no_momentum_expires_after_window():
    opened = time.time() - 300
    o = _momentum_order(opened_at=opened)
    action, reason, _ = o.evaluate(0.95, time.time())
    assert action == Action.HOLD
    action, reason, _ = o.evaluate(0.79, time.time())
    assert action == Action.CLOSE and reason == "hard_stop"


def test_hard_stop_ignores_buy_slip_entry():
    """−25% from open_mark must NOT stop when buy slip made entry 5% higher."""
    o = _order(mark=1.0, buy_slip=0.05)
    assert abs(o.entry_price - 1.05) < 1e-12
    assert o.open_mark == 1.0
    action, reason, _ = o.evaluate(0.75, time.time())
    assert action == Action.HOLD and reason is None
    action, reason, _ = o.evaluate(0.70, time.time())
    assert action == Action.CLOSE and reason == "hard_stop"


def test_stage1_recovers_notional_after_sell_slip():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.05)
    # cost_basis=1.0; stage1 when mark >= 1.25
    mark = 1.25
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
    action, reason, _ = o.evaluate(0.70, time.time())
    assert action == Action.CLOSE and reason == "hard_stop"


def test_trail_not_before_stage1():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.note_mark(1.25)
    # 30% off peak would be trail after stage1; before stage1 must hold
    action, reason, _ = o.evaluate(0.875, time.time())
    assert action == Action.HOLD
    assert reason is None


def test_trail_after_stage1():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.stage1_done = True
    o.qty = 5
    o.peak_price = 2.0
    action, reason, _ = o.evaluate(1.4, time.time())  # 30% off peak
    assert action == Action.CLOSE and reason == "trail"


def test_pre_stage1_trail_closes_before_stage1_target():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.pre_stage1_trail_enable = True
    o.pre_stage1_trail_activate_pct = 0.15
    o.pre_stage1_trail_drawdown_pct = 0.40
    # Pumped to 1.20 (>= open_mark*1.15) but never reached stage1_tp target (1.25).
    # Pre-stage1 trail threshold = 1.20*(1-0.40) = 0.72, above the hard_stop
    # threshold of 0.70, so 0.71 trips the trail without also tripping hard_stop.
    o.note_mark(1.20)
    action, reason, qty = o.evaluate(0.71, time.time())
    assert action == Action.CLOSE and reason == "pre_stage1_trail" and qty == o.qty


def test_pre_stage1_trail_disabled_by_default():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.note_mark(1.20)
    # hard_stop threshold is 0.70; pick a mark above it but below the pre-stage1 trail
    # trigger to prove the (disabled) feature does not fire.
    action, reason, _ = o.evaluate(0.72, time.time())
    assert action == Action.HOLD and reason is None


def test_timeout_extended_when_profitable():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.timeout_hours = 2.0
    o.timeout_extend_if_profitable = True
    o.timeout_extend_hours = 1.0
    o.stage1_done = True
    o.cost_basis = 1.0
    now = o.opened_at + 2.5 * 3600  # past base timeout, within extended window
    action, reason, _ = o.evaluate(1.1, now)  # profitable (mark > cost_basis)
    assert action == Action.HOLD and reason is None
    later = o.opened_at + 3.5 * 3600  # past extended timeout too
    action, reason, _ = o.evaluate(1.1, later)
    assert action == Action.CLOSE and reason == "timeout"


def test_timeout_not_extended_when_unprofitable():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.timeout_hours = 2.0
    o.timeout_extend_if_profitable = True
    o.timeout_extend_hours = 1.0
    o.stage1_done = True
    o.cost_basis = 1.0
    now = o.opened_at + 2.5 * 3600  # past base timeout
    action, reason, _ = o.evaluate(0.95, now)  # not profitable (mark <= cost_basis)
    assert action == Action.CLOSE and reason == "timeout"


def test_base_timeout_before_stage1_beats_late_stage1_target():
    """Past base timeout must close even if mark just hit stage1 — no extend rescue."""
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.timeout_hours = 2.0
    o.timeout_extend_if_profitable = True
    o.timeout_extend_hours = 1.0
    o.stage1_done = False
    o.cost_basis = 1.0
    now = o.opened_at + 2.1 * 3600
    action, reason, qty = o.evaluate(1.30, now)  # would be stage1 if under timeout
    assert action == Action.CLOSE and reason == "timeout" and qty == o.qty


def test_trail_dynamic_tightens_at_high_multiples():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.stage1_done = True
    o.qty = 5
    o.trail_dynamic = True
    o.peak_price = 6.0  # peak/open_mark = 6 > 5 -> tightened to 15%
    # 20% off peak (would NOT trigger the default 30% trail) but exceeds 15% tightened trail
    action, reason, _ = o.evaluate(4.8, time.time())
    assert action == Action.CLOSE and reason == "trail"


def test_trail_dynamic_disabled_uses_flat_drawdown():
    o = _order(mark=1.0, buy_slip=0.0, sell_slip=0.0)
    o.stage1_done = True
    o.qty = 5
    o.trail_dynamic = False
    o.peak_price = 6.0
    # Same 20% pullback that tightened trail would close, but flat 30% must hold.
    action, reason, _ = o.evaluate(4.8, time.time())
    assert action == Action.HOLD and reason is None
