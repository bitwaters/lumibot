from lumibot.filters import apply_push_snapshot, flatten_token_info, extract_trending_fields
from lumibot.models import Source, TokenCandidate


def test_flatten_token_info_reads_nested_stat_top10():
    flat = flatten_token_info(
        {
            "liquidity": "1000",
            "stat": {"top_10_holder_rate": "0.22", "holder_count": 500},
            "pool": {"liquidity": "2000"},
        }
    )
    fields = extract_trending_fields(flat)
    assert fields["top10_rate"] == 0.22
    assert fields["holder_count"] == 500
    assert fields["liquidity"] == 1000.0  # top-level wins


def test_apply_push_snapshot_overwrites_gate_fields():
    cand = TokenCandidate(
        chain="sol",
        address="t",
        source=Source.SIGNAL,
        symbol="OLD",
        market_cap=100_000,
        liquidity=10_000,
        holder_count=100,
        top10_rate=0.4,
        visiting_count=50,
        price=1.0,
    )
    apply_push_snapshot(
        cand,
        {
            "symbol": "NEW",
            "liquidity": 55_000,
            "visiting_count": 400,
            "stat": {"top_10_holder_rate": 0.15, "holder_count": 900},
            "open_timestamp": 1_700_000_000,
        },
        price=2.0,
        market_cap=220_000,
    )
    assert cand.symbol == "NEW"
    assert cand.price == 2.0
    assert cand.market_cap == 220_000
    assert cand.liquidity == 55_000
    assert cand.holder_count == 900
    assert cand.top10_rate == 0.15
    assert cand.visiting_count == 400
    assert cand.open_timestamp == 1_700_000_000
