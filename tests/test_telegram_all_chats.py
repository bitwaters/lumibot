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
