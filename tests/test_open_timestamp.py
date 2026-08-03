from lumibot.filters import merge_info_fields, parse_open_timestamp
from lumibot.models import Source, TokenCandidate


def test_parse_open_timestamp_seconds_and_ms():
    assert parse_open_timestamp({"open_timestamp": 1_700_000_000}) == 1_700_000_000
    assert parse_open_timestamp({"open_timestamp": 1_700_000_000_000}) == 1_700_000_000
    assert parse_open_timestamp({}) is None


def test_parse_open_timestamp_ignores_creation_timestamp():
    assert parse_open_timestamp({"creation_timestamp": 1_700_000_000}) is None
    assert (
        parse_open_timestamp(
            {"creation_timestamp": 1_700_000_000, "open_timestamp": 1_800_000_000}
        )
        == 1_800_000_000
    )


def test_merge_info_fills_open_timestamp_only_when_missing():
    cand = TokenCandidate(
        chain="sol",
        address="t",
        source=Source.TRENDING,
        open_timestamp=111.0,
    )
    merge_info_fields(cand, {"open_timestamp": 222.0})
    assert cand.open_timestamp == 111.0
    cand2 = TokenCandidate(chain="sol", address="t", source=Source.TRENDING)
    merge_info_fields(cand2, {"open_timestamp": 222.0})
    assert cand2.open_timestamp == 222.0
