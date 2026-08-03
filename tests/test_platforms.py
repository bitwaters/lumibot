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


def _cand(platform: str | None = "pump") -> TokenCandidate:
    return TokenCandidate(
        chain="sol",
        address="T",
        source=Source.TRENDING,
        market_cap=40_000,
        liquidity=20_000,
        top10_rate=0.2,
        holder_count=200,
        visiting_count=150,
        platform=platform,
    )


def test_empty_platforms_allow_all():
    assert apply_light_filters(_cand("anything"), SOL, platforms=[]).ok


def test_nonempty_platforms_rejects_other():
    r = apply_light_filters(_cand("raydium"), SOL, platforms=["pump"])
    assert not r.ok and r.reason == "platform"


def test_nonempty_platforms_accepts_allowlisted():
    assert apply_light_filters(_cand("Pump"), SOL, platforms=["pump"]).ok


def test_nonempty_platforms_missing_platform_fails_closed():
    r = apply_light_filters(_cand(None), SOL, platforms=["pump"])
    assert not r.ok and r.reason == "platform_missing"
