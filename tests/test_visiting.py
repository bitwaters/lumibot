from lumibot.filters import merge_info_fields
from lumibot.models import Source, TokenCandidate


def test_signal_force_visiting_clears_payload_fallback():
    cand = TokenCandidate(
        chain="sol",
        address="T",
        source=Source.SIGNAL,
        visiting_count=999,  # stale payload value should be wiped
    )
    merge_info_fields(cand, {"liquidity": 1}, force_visiting=True)
    assert cand.visiting_count is None


def test_signal_force_visiting_uses_info():
    cand = TokenCandidate(
        chain="sol",
        address="T",
        source=Source.SIGNAL,
        visiting_count=999,
    )
    merge_info_fields(cand, {"visiting_count": 120}, force_visiting=True)
    assert cand.visiting_count == 120


def test_trending_visiting_not_overwritten_by_info():
    cand = TokenCandidate(
        chain="sol",
        address="T",
        source=Source.TRENDING,
        visiting_count=200,
        liquidity=None,
    )
    merge_info_fields(
        cand,
        {"liquidity": 20_000, "visiting_count": 50},
        force_visiting=False,
    )
    assert cand.visiting_count == 200
    assert cand.liquidity == 20_000


def test_trending_visiting_not_filled_from_info_when_missing():
    cand = TokenCandidate(
        chain="sol",
        address="T",
        source=Source.TRENDING,
        visiting_count=None,
    )
    merge_info_fields(cand, {"visiting_count": 200}, force_visiting=False)
    assert cand.visiting_count is None
