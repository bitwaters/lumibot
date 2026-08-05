import pytest

from lumibot.models import Source, TokenCandidate
from lumibot.telegram_notify import TelegramNotifier


@pytest.mark.asyncio
async def test_send_requires_all_chats(monkeypatch):
    n = TelegramNotifier("000:fake", [1, 2])
    calls: list[int] = []

    async def fake_send(chat_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        calls.append(chat_id)
        if chat_id == 2:
            raise RuntimeError("boom")
        return type("X", (), {"message_id": chat_id})

    monkeypatch.setattr(n._bot, "send_message", fake_send)
    cand = TokenCandidate(chain="sol", address="T", source=Source.TRENDING, symbol="X")
    any_ok, all_ok, _ = await n.send_candidate(cand)
    assert any_ok is True and all_ok is False
    assert calls == [1, 2]
    await n.close()


@pytest.mark.asyncio
async def test_send_all_ok(monkeypatch):
    n = TelegramNotifier("000:fake", [1, 2])

    async def fake_send(chat_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        return type("X", (), {"message_id": chat_id})

    monkeypatch.setattr(n._bot, "send_message", fake_send)
    cand = TokenCandidate(chain="sol", address="T", source=Source.TRENDING, symbol="X")
    assert await n.send_candidate(cand) == (True, True, [(1, 1), (2, 2)])
    await n.close()


@pytest.mark.asyncio
async def test_send_all_fail(monkeypatch):
    n = TelegramNotifier("000:fake", [1])

    async def fake_send(chat_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(n._bot, "send_message", fake_send)
    cand = TokenCandidate(chain="sol", address="T", source=Source.TRENDING, symbol="X")
    assert await n.send_candidate(cand) == (False, False, [])
    await n.close()


@pytest.mark.asyncio
async def test_edit_text_partial_success(monkeypatch):
    n = TelegramNotifier("000:fake", [1, 2])
    edited: list[tuple[int, int]] = []

    async def fake_edit(chat_id, message_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        edited.append((chat_id, message_id))
        if chat_id == 2:
            raise RuntimeError("edit boom")
        return None

    monkeypatch.setattr(n._bot, "edit_message_text", fake_edit)
    ok, all_ok = await n.edit_text(
        "new body", [(1, 11), (2, 22)], reply_markup=None, disable_preview=True
    )
    assert ok is True and all_ok is False
    assert edited == [(1, 11), (2, 22)]
    await n.close()


@pytest.mark.asyncio
async def test_edit_text_all_fail(monkeypatch):
    n = TelegramNotifier("000:fake", [1, 2])

    async def fake_edit(chat_id, message_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        raise RuntimeError("edit down")

    monkeypatch.setattr(n._bot, "edit_message_text", fake_edit)
    ok, all_ok = await n.edit_text("new body", [(1, 11), (2, 22)])
    assert ok is False and all_ok is False
    await n.close()


@pytest.mark.asyncio
async def test_edit_text_empty_ids_short_circuits(monkeypatch):
    n = TelegramNotifier("000:fake", [1])
    called = False

    async def fake_edit(chat_id, message_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(n._bot, "edit_message_text", fake_edit)
    ok, all_ok = await n.edit_text("new body", [])
    assert (ok, all_ok) == (False, False)
    assert called is False
    await n.close()


@pytest.mark.asyncio
async def test_edit_failure_leaves_original_and_other_chats_edit(monkeypatch):
    n = TelegramNotifier("000:fake", [1, 2])
    calls: list[int] = []
    bodies: list[str] = []

    async def fake_edit(chat_id, message_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        calls.append(chat_id)
        bodies.append(text)
        if chat_id == 1:
            raise RuntimeError("edit boom")

    monkeypatch.setattr(n._bot, "edit_message_text", fake_edit)
    ok, all_ok = await n.edit_text("frozen body", [(1, 11), (2, 22)])
    assert ok is True and all_ok is False
    assert calls == [1, 2]
    assert bodies == ["frozen body", "frozen body"]
    await n.close()


@pytest.mark.asyncio
async def test_paper_events_skip_group_chats(monkeypatch):
    """Trade events (stage1/closes) must only reach control chats, not groups."""
    n = TelegramNotifier("000:fake", [1, -100], event_chat_ids=[1])
    calls: list[int] = []

    async def fake_send(chat_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        calls.append(chat_id)
        return type("X", (), {"message_id": chat_id})

    monkeypatch.setattr(n._bot, "send_message", fake_send)
    from lumibot.exec_types import PaperTradeEvent

    ev = PaperTradeEvent(
        kind="close",
        chain="sol",
        token="T",
        symbol="X",
        reason="hard_stop",
        mark=0.7,
        fill_price=0.66,
        qty=20.0,
        pnl=-6.0,
        notional_usd=20.0,
        entry_price=1.05,
        open_mark=1.0,
        hold_sec=60,
    )
    ok, all_ok = await n.send_paper_event(ev)
    assert (ok, all_ok) == (True, True)
    # Group chat id -100 must NOT receive the trade event.
    assert calls == [1]
    await n.close()


def test_gmgn_keyboard_uniform_across_chains():
    """All chains must render the same button set (GMGN + DexScreemer)."""
    from lumibot.telegram_notify import gmgn_keyboard

    for chain in ("sol", "bsc", "robinhood"):
        kb = gmgn_keyboard(chain, "0xABC")
        texts = [b.text for row in kb.inline_keyboard for b in row]
        assert texts == ["打开 GMGN", "DexScreener"], (chain, texts)
