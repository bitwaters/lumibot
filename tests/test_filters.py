from lumibot.config import FiltersCfg
from lumibot.filters import apply_light_filters, evaluate_chase
from lumibot.models import Source, TokenCandidate


SOL = FiltersCfg(
    mc_min=1_000,
    mc_max=50_000,
    liquidity_min=5_000,
    top10_max=0.30,
    holders_min=100,
    visiting_min=100,
)


def _base(**kwargs) -> TokenCandidate:
    data = dict(
        chain="sol",
        address="Tok",
        source=Source.SIGNAL,
        signal_type=12,
        market_cap=40_000,
        trigger_mc=40_000,
        liquidity=20_000,
        top10_rate=0.2,
        holder_count=200,
        visiting_count=150,
    )
    data.update(kwargs)
    return TokenCandidate(**data)


def test_signal_dual_mc_rejects_low_trigger():
    cand = _base(trigger_mc=500)
    r = apply_light_filters(cand, SOL)
    assert not r.ok and r.reason == "trigger_mc"


def test_missing_liq_fail_closed():
    cand = _base(liquidity=None)
    r = apply_light_filters(cand, SOL)
    assert not r.ok and r.reason == "liq_missing"


def test_sol_defaults_pass():
    assert apply_light_filters(_base(), SOL).ok


def test_visiting_gate_uniform_across_sources():
    """One threshold per chain: signal and trending both gate on visiting_min."""
    cfg = FiltersCfg(
        mc_min=1_000,
        mc_max=50_000,
        liquidity_min=5_000,
        top10_max=0.30,
        holders_min=100,
        visiting_min=200,
    )
    signal = _base(source=Source.SIGNAL, visiting_count=220)
    assert apply_light_filters(signal, cfg).ok
    trending = _base(source=Source.TRENDING, signal_type=None, visiting_count=220)
    assert apply_light_filters(trending, cfg).ok

    low = _base(source=Source.TRENDING, signal_type=None, visiting_count=199)
    r = apply_light_filters(low, cfg)
    assert not r.ok and r.reason == "visiting"


def test_chase_rejects_when_market_ran_past_push():
    cfg = FiltersCfg(
        mc_min=1_000,
        mc_max=50_000,
        liquidity_min=5_000,
        top10_max=0.30,
        holders_min=100,
        visiting_min=100,
        chase_max_pct=0.10,
    )
    cand = _base(push_price=1.0)
    assert evaluate_chase(cand, 1.05, cfg) is False   # +5% < 10%: ok
    assert evaluate_chase(cand, 1.10, cfg) is False   # exactly at 10%: not "more than"
    assert evaluate_chase(cand, 1.25, cfg) is True    # +25%: chasing the top


def test_chase_uniform_across_sources():
    """One chase threshold per chain applies to both sources."""
    cfg = FiltersCfg(
        mc_min=1_000,
        mc_max=50_000,
        liquidity_min=5_000,
        top10_max=0.30,
        holders_min=100,
        visiting_min=100,
        chase_max_pct=0.10,
    )
    # Trending references its payload price (no push_price) with the same gate.
    trend = _base(source=Source.TRENDING, signal_type=None, price=1.0)
    assert evaluate_chase(trend, 1.05, cfg) is False
    assert evaluate_chase(trend, 1.15, cfg) is True
    # Signal uses push_price with the same gate.
    sig = _base(push_price=1.0)
    assert evaluate_chase(sig, 1.15, cfg) is True

    off = cfg.model_copy(update={"chase_max_pct": 0.0})
    assert evaluate_chase(sig, 2.0, off) is False

    # Missing payload price / missing quote can't trigger either.
    assert evaluate_chase(_base(push_price=None), 2.0, cfg) is False
    assert evaluate_chase(_base(price=None), 2.0, cfg) is False
    assert evaluate_chase(_base(push_price=1.0), None, cfg) is False
