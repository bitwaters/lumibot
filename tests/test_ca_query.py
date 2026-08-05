import asyncio

import pytest


@pytest.fixture(autouse=True)
def _clear_probe_miss_cache():
    from lumibot.telegram_bot import _probe_miss_cache

    _probe_miss_cache.clear()
    yield
    _probe_miss_cache.clear()

from lumibot.config import load_app_config
from lumibot.models import NormalizedSafety, Source, TokenCandidate
from lumibot.telegram_bot import (
    _chain_candidates,
    _extract_ca,
    _handle_ca_message,
    _query_token,
)
from lumibot.telegram_notify import render_query_card

EVM = "0xcd827de09ad3f2a8d9e47f36b8cb2635aa700932"
SOL = "61t6VGc1pEoGJLtr5gYveG4LarhTGrhJhtYdMNiMpump"


def _app():
    return load_app_config("config/chains.yaml")


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.infos: dict[tuple[str, str], dict | Exception] = {}
        self.secs: dict[tuple[str, str], dict | Exception] = {}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.cache_flags: list[bool] = []
        self.infos: dict[tuple[str, str], dict | Exception] = {}
        self.secs: dict[tuple[str, str], dict | Exception] = {}

    async def get_token_info(self, chain, address, *, use_cache=True):
        self.calls.append((chain, address))
        self.cache_flags.append(use_cache)
        v = self.infos.get((chain, address), {})
        if isinstance(v, Exception):
            raise v
        return v

    async def get_token_security(self, chain, address, *, use_cache=True):
        self.cache_flags.append(use_cache)
        v = self.secs.get((chain, address), {})
        if isinstance(v, Exception):
            raise v
        return v


def _info(**kw) -> dict:
    base = {"symbol": "MUSK", "market_cap": 27_700, "liquidity": 15_600}
    base.update(kw)
    return base


def test_extract_ca_evm_embedded():
    assert _extract_ca(f"看看这个 {EVM} 怎么样") == EVM
    assert _extract_ca(f"https://gmgn.ai/token/{EVM}?x=1") == EVM


def test_extract_ca_solana():
    assert _extract_ca(f"买入 {SOL} ！") == SOL


def test_extract_ca_evm_not_matched_as_solana():
    assert _extract_ca(EVM) == EVM


def test_extract_ca_first_of_many():
    other_evm = "0x" + "a" * 40
    assert _extract_ca(f"{other_evm} 和 {EVM}") == other_evm


def test_extract_ca_none():
    assert _extract_ca("随便聊聊，没有地址") is None
    assert _extract_ca("0x123") is None
    assert _extract_ca("shortbase58") is None


def test_chain_candidates_sol_by_format():
    assert _chain_candidates(SOL, _app()) == ["sol"]


def test_chain_candidates_evm_by_probe_order():
    assert _chain_candidates(EVM, _app()) == ["bsc", "robinhood"]


@pytest.mark.asyncio
async def test_query_token_sol_direct():
    client = FakeClient()
    client.infos[("sol", SOL)] = _info(
        wallet_tags_stat={"smart_wallets": 16, "renowned_wallets": 4}
    )
    chain, cand, info = await _query_token(client, SOL, _app())
    assert chain == "sol"
    assert cand is not None and cand.symbol == "MUSK"
    assert cand.smart_wallets == 16
    assert cand.kol_wallets == 4
    assert client.calls == [("sol", SOL)]


@pytest.mark.asyncio
async def test_query_token_empty_shell_moves_on():
    client = FakeClient()
    client.infos[("bsc", EVM)] = {"symbol": "", "address": "", "price": {"price": "0"}}
    client.infos[("robinhood", EVM)] = _info()
    chain, _c, _i = await _query_token(client, EVM, _app())
    assert chain == "robinhood"


@pytest.mark.asyncio
async def test_query_token_bsc_hit_no_rh_probe():
    client = FakeClient()
    client.infos[("bsc", EVM)] = _info()
    chain, cand, infod = await _query_token(client, EVM, _app())
    assert chain == "bsc"
    assert client.calls == [("bsc", EVM)]


@pytest.mark.asyncio
async def test_query_token_bsc_404_falls_over_to_rh():
    client = FakeClient()
    client.infos[("bsc", EVM)] = RuntimeError("HTTP 404")
    client.infos[("robinhood", EVM)] = _info()
    chain, cand, infod = await _query_token(client, EVM, _app())
    assert chain == "robinhood"
    assert client.calls == [("bsc", EVM), ("robinhood", EVM)]


@pytest.mark.asyncio
async def test_query_token_all_miss():
    client = FakeClient()
    client.infos[("bsc", EVM)] = RuntimeError("HTTP 404")
    client.infos[("robinhood", EVM)] = {}
    chain, cand, infod = await _query_token(client, EVM, _app())
    assert chain is None and cand is None


@pytest.mark.asyncio
async def test_query_token_empty_info_moves_on():
    client = FakeClient()
    client.infos[("bsc", EVM)] = {}
    client.infos[("robinhood", EVM)] = _info()
    chain, _c, _i = await _query_token(client, EVM, _app())
    assert chain == "robinhood"


def test_query_card_layout():
    cand = TokenCandidate(
        chain="bsc",
        address=EVM,
        source=Source.TRENDING,
        symbol="MUSK",
        price=0.000123,
        market_cap=27_700,
        liquidity=15_600,
        top10_rate=0.163,
        holder_count=295,
        visiting_count=4,
        volume_1h=None,
        platform="flap",
        open_timestamp=1_700_000_000,
        smart_wallets=16,
        kol_wallets=4,
        safety=NormalizedSafety(sell_tax=0.01),
    )
    text = render_query_card(cand)
    assert text.startswith("🔍 <b>$MUSK</b> · BSC")
    assert f"📍 CA: <code>{EVM}</code>" in text
    assert "<code>💰 价格    0.000123</code>" in text
    assert "<code>💰 市值    ≈ $27.7K</code>" in text
    assert "🔥 热度" in text
    assert "🦈 聪明钱" in text and "🎩 KOL" in text
    assert "卖税 1.0%" in text
    assert "已开仓" not in text
    assert "⏱ 延迟" not in text


def test_query_card_hides_sm_kol_when_absent():
    cand = TokenCandidate(
        chain="sol", address=SOL, source=Source.TRENDING, symbol="X", market_cap=10_000
    )
    text = render_query_card(cand)
    assert "🦈 聪明钱" not in text
    assert "🎩 KOL" not in text


def test_query_card_missing_metrics_dash():
    cand = TokenCandidate(chain="sol", address=SOL, source=Source.TRENDING, symbol="X")
    text = render_query_card(cand)
    assert "<code>💰 价格    —</code>" in text
    assert "<code>💰 市值    —</code>" in text
    assert "🛡 安全 未知" in text


def test_query_card_hard_fail_still_renders():
    cand = TokenCandidate(
        chain="sol",
        address=SOL,
        source=Source.TRENDING,
        symbol="X",
        safety=NormalizedSafety(hard_fail=True, reason="safety_honeypot", warnings=["honeypot"]),
    )
    text = render_query_card(cand)
    assert "🔍 <b>$X</b> · SOL" in text
    assert "安全" in text


@pytest.mark.asyncio
async def test_handle_ca_message_success():
    client = FakeClient()
    client.infos[("bsc", EVM)] = _info()
    replies: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))

    handled = await _handle_ca_message(
        chat_id=1, text=f"查 {EVM}", client=client, app_cfg=_app(), throttle={}, reply=reply
    )
    assert handled is True
    assert len(replies) == 1
    text = replies[0][0][0]
    kwargs = replies[0][1]
    assert text.startswith("🔍 <b>$MUSK</b>")
    assert kwargs["parse_mode"] == "HTML"
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_handle_ca_message_throttled():
    client = FakeClient()
    replies: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))

    throttle: dict[int, float] = {1: 1_000_000_000_000}
    handled = await _handle_ca_message(
        chat_id=1, text=EVM, client=client, app_cfg=_app(), throttle=throttle, reply=reply
    )
    assert handled is True
    assert "查询太频繁" in replies[0][0][0]
    assert client.calls == []


@pytest.mark.asyncio
async def test_handle_ca_message_gmgn_down():
    client = FakeClient()
    client.infos[("bsc", EVM)] = RuntimeError("GMGN IP banned")
    replies: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))

    handled = await _handle_ca_message(
        chat_id=1, text=EVM, client=client, app_cfg=_app(), throttle={}, reply=reply
    )
    assert handled is True
    assert "GMGN 暂时不可用" in replies[0][0][0]


@pytest.mark.asyncio
async def test_handle_ca_message_not_found():
    client = FakeClient()
    replies: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))

    handled = await _handle_ca_message(
        chat_id=1, text=EVM, client=client, app_cfg=_app(), throttle={}, reply=reply
    )
    assert handled is True
    assert "未找到该合约" in replies[0][0][0]


@pytest.mark.asyncio
async def test_handle_ca_message_no_ca_passthrough():
    client = FakeClient()
    replies: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))

    handled = await _handle_ca_message(
        chat_id=1, text="普通消息", client=client, app_cfg=_app(), throttle={}, reply=reply
    )
    assert handled is False
    assert replies == []


@pytest.mark.asyncio
async def test_handle_ca_message_disabled():
    client = FakeClient()
    replies: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))

    app = _app()
    app.global_.ca_query.enabled = False
    handled = await _handle_ca_message(
        chat_id=1, text=EVM, client=client, app_cfg=app, throttle={}, reply=reply
    )
    assert handled is False


class FakeNarrative:
    def __init__(self, line: str | None = None, error: bool = False) -> None:
        self.line = line
        self.error = error

    async def narrative_for(self, cand, info):
        if self.error:
            raise RuntimeError("llm down")
        return self.line


class _FakeSent:
    def __init__(self, text: str, edits: list) -> None:
        self.text = text
        self.reply_markup = None
        self.chat = type("C", (), {"id": 1})()
        self.message_id = 42
        self.edits = edits

        async def fake_edit(*args, **kwargs):
            edits.append((args, kwargs))

        self.bot = type("B", (), {"edit_message_text": fake_edit})()


@pytest.mark.asyncio
async def test_handle_ca_message_narrative_async_edit():
    client = FakeClient()
    client.infos[("bsc", EVM)] = _info(
        price={"price": "1.0", "price_24h": "0.5", "buys_24h": 1200, "sells_24h": 800}
    )
    replies: list[tuple] = []
    edits: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))
        return _FakeSent(args[0], edits)

    handled = await _handle_ca_message(
        chat_id=1,
        text=EVM,
        client=client,
        app_cfg=_app(),
        throttle={},
        reply=reply,
        narrative=FakeNarrative(line="马斯克概念 meme，社区热度高"),
    )
    assert handled is True
    # Reply is immediate and does NOT contain the narrative (async edit).
    assert "📚" not in replies[0][0][0]
    await asyncio.sleep(0.05)
    assert edits, "narrative edit task should have fired"
    edited_text = edits[0][1]["text"]
    assert "📚 马斯克概念 meme，社区热度高" in edited_text
    assert "24h" not in edited_text
    assert "🛒 买" in edited_text and "1,200" in edited_text
    assert "💸 卖" in edited_text


@pytest.mark.asyncio
async def test_handle_ca_message_narrative_fail_open():
    client = FakeClient()
    client.infos[("bsc", EVM)] = _info()
    replies: list[tuple] = []

    async def reply(*args, **kwargs):
        replies.append((args, kwargs))

    handled = await _handle_ca_message(
        chat_id=1,
        text=EVM,
        client=client,
        app_cfg=_app(),
        throttle={},
        reply=reply,
        narrative=FakeNarrative(error=True),
    )
    assert handled is True
    assert "📚" not in replies[0][0][0]
    assert replies[0][0][0].startswith("🔍 <b>$MUSK</b>")


def test_market_cap_computed_from_price_times_supply():
    from lumibot.telegram_bot import _market_cap_from_info

    info = {
        "price": {"price": "0.000017897718"},
        "circulating_supply": "1000000000",
    }
    assert _market_cap_from_info(info) is not None
    assert abs(_market_cap_from_info(info) - 17_897.718) < 1.0
    assert _market_cap_from_info({"price": None, "circulating_supply": "1"}) is None
    assert _market_cap_from_info({"price": {"price": "0"}, "circulating_supply": "1"}) is None


@pytest.mark.asyncio
async def test_query_token_computes_market_cap():
    client = FakeClient()
    client.infos[("bsc", EVM)] = _info(
        price={"price": "0.000017897718", "volume_1h": "21874.86", "buys_24h": 1172, "sells_24h": 943},
        circulating_supply="1000000000",
    )
    chain, cand, _ = await _query_token(client, EVM, _app())
    assert chain == "bsc"
    assert cand.market_cap is not None and cand.market_cap > 10_000
    assert cand.volume_1h == 21_874.86


def test_query_card_shows_volume_and_mc():
    cand = TokenCandidate(
        chain="bsc", address=EVM, source=Source.TRENDING, symbol="MUSK",
        market_cap=17_897, volume_1h=21_874.86, liquidity=6_000, holder_count=106,
    )
    text = render_query_card(cand)
    assert "市值    ≈ $17.9K" in text
    assert "1H 成交 $21.9K" in text


def test_narrative_block_sentence_and_links():
    from lumibot.telegram_notify import render_narrative_block

    info = {"link": {"twitter_username": "RealTrump", "website": "https://trump.fun"}}
    block = render_narrative_block(info, "特朗普概念官方迷因币，X 讨论度上升")
    assert block.splitlines()[0] == "📚 特朗普概念官方迷因币，X 讨论度上升"
    assert '<a href="https://x.com/RealTrump">X</a>' in block
    assert '<a href="https://trump.fun">官网</a>' in block
    assert "24h" not in block
    # links render even when the sentence is N/A
    block_only_links = render_narrative_block(info, None)
    assert block_only_links == block.splitlines()[1]
    # no info and no sentence -> empty
    assert render_narrative_block(None, None) == ""


@pytest.mark.asyncio
async def test_query_served_from_cache_first():
    client = FakeClient()
    client.infos[("bsc", EVM)] = _info()
    _, _, _ = await _query_token(client, EVM, _app())
    # Cache-first: queries use the shared token-info/security caches (millisecond
    # replies for hot tokens); fresh fetch only happens on cache miss.
    assert client.cache_flags == [True, True], client.cache_flags


@pytest.mark.asyncio
async def test_probe_miss_cache_skips_known_misses():
    from lumibot.telegram_bot import _probe_miss_cache

    client = FakeClient()
    client.infos[("bsc", EVM)] = {}  # empty shell
    client.infos[("robinhood", EVM)] = _info()
    chain, _, _ = await _query_token(client, EVM, _app())
    assert chain == "robinhood"
    assert client.calls == [("bsc", EVM), ("robinhood", EVM)]
    # second query: bsc miss remembered -> skip straight to robinhood cache
    client2 = FakeClient()
    client2.infos[("robinhood", EVM)] = _info()
    chain2, _, _ = await _query_token(client2, EVM, _app())
    assert chain2 == "robinhood"
    assert client2.calls == [("robinhood", EVM)]
    _probe_miss_cache.clear()


def test_extract_social_links_labels_and_dedupe():
    from lumibot.narrative import extract_social_links

    info = {
        "link": {
            "twitter_username": "RealTrump",
            "website": "https://trump.fun",
            "telegram": "https://t.me/trump_token",
            "discord": "https://discord.gg/trump",
            "gmgn": "https://gmgn.ai/bsc/token/0x",
            "geckoterminal": "https://geckoterminal.com/x",
        }
    }
    links = extract_social_links(info)
    assert links == [
        '<a href="https://x.com/RealTrump">X</a>',
        '<a href="https://trump.fun">官网</a>',
        '<a href="https://t.me/trump_token">TG</a>',
        '<a href="https://discord.gg/trump">DC</a>',
    ]


def test_extract_social_links_cto_label():
    from lumibot.narrative import extract_social_links

    info = {
        "dev": {"cto_flag": "1"},
        "link": {"twitter_username": "CTOToken", "telegram": "https://t.me/cto_community"},
    }
    links = extract_social_links(info)
    assert any("<a href=\"https://t.me/cto_community\">社区</a>" == l for l in links)
    assert not any(">TG</a>" == l[-5:] for l in links)


def test_extract_social_links_rejects_bad_inputs():
    from lumibot.narrative import extract_social_links

    # injection / spoof / tweet-path username / non-http
    info = {
        "link": {
            "twitter_username": 'bad" onmouseover="x',
            "website": "javascript:alert(1)",
            "telegram": "https://evil.com/\" onclick=\"x",
        }
    }
    assert extract_social_links(info) == []
    # tweet URL path value -> omitted (not a plain username)
    info2 = {"link": {"twitter_username": "boycott_pumpfun/status/20846777785494286"}}
    assert extract_social_links(info2) == []
    # spoofed domain still renders as 官网 hyperlink (label hides domain; confirm dialog shows URL)
    info3 = {"link": {"website": "https://gmgn.ai.evil.com"}}
    links = extract_social_links(info3)
    assert len(links) == 1 and '<a href="https://gmgn.ai.evil.com">官网</a>' in links[0]
    assert extract_social_links(None) == []
    assert extract_social_links({}) == []
