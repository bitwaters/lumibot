from lumibot.config import FiltersCfg
from lumibot.filters import apply_light_filters
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
