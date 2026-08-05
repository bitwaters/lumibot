from __future__ import annotations

from lumibot.config import NewsCfg
from lumibot.models import Source, TokenCandidate
from lumibot.news import NewsPoller


class FakeOpenNewsClient:
    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = responses
        self.queries: list[str] = []

    async def search(self, query: str, limit: int = 10):  # noqa: ARG002, ANN001
        self.queries.append(query)
        return self.responses.get(query, [])


async def test_match_news_prefers_token_level_news():
    client = FakeOpenNewsClient(
        {
            "PEPE TEST": [
                {"title": "token hit title", "summary": "token-specific update", "score": 0.95}
            ],
            "SOL meme": [
                {"title": "market hit title", "summary": "market-wide update", "score": 0.99}
            ],
        }
    )
    cfg = NewsCfg(enabled=True)
    poller = NewsPoller(client, cfg)

    cand = TokenCandidate(
        chain="sol",
        address="T",
        source=Source.SIGNAL,
        symbol="PEPE",
        name="TEST",
        market_cap=40_000,
        liquidity=10_000,
        top10_rate=0.1,
        holder_count=100,
    )
    line = await poller.match_news(cand)

    assert line == "📰 相关 token-specific update"
    assert client.queries == ["PEPE TEST"]


async def test_match_news_skips_token_for_short_symbol_uses_market():
    client = FakeOpenNewsClient(
        {
            "SOL meme": [
                {"title": "market hit title", "summary": "market-wide update", "score": 0.95}
            ],
        }
    )
    cfg = NewsCfg(enabled=True, market_keywords=["meme"], market_coins=["SOL"])
    poller = NewsPoller(client, cfg)
    await poller._refresh_markets()

    cand = TokenCandidate(
        chain="sol",
        address="T",
        source=Source.SIGNAL,
        symbol="PE",
        name="TEST",
        market_cap=40_000,
        liquidity=10_000,
        top10_rate=0.1,
        holder_count=100,
    )
    line = await poller.match_news(cand)

    assert line == "📰 市场 market-wide update"
    assert client.queries == ["SOL meme"]


async def test_match_news_requires_market_score_threshold():
    client = FakeOpenNewsClient(
        {
            "SOL meme": [
                {"title": "market hit title", "summary": "low score", "score": 0.2}
            ],
        }
    )
    cfg = NewsCfg(
        enabled=True, market_keywords=["meme"], min_score=0.8, market_coins=["SOL"]
    )
    poller = NewsPoller(client, cfg)
    await poller._refresh_markets()

    cand = TokenCandidate(
        chain="sol",
        address="T",
        source=Source.SIGNAL,
        symbol="PE",
        name="TEST",
        market_cap=40_000,
        liquidity=10_000,
        top10_rate=0.1,
        holder_count=100,
    )
    line = await poller.match_news(cand)

    assert line is None
    assert client.queries == ["SOL meme"]
