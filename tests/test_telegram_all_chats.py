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

    monkeypatch.setattr(n._bot, "send_message", fake_send)
    cand = TokenCandidate(chain="sol", address="T", source=Source.TRENDING, symbol="X")
    any_ok, all_ok = await n.send_candidate(cand)
    assert any_ok is True and all_ok is False
    assert calls == [1, 2]
    await n.close()


@pytest.mark.asyncio
async def test_send_all_ok(monkeypatch):
    n = TelegramNotifier("000:fake", [1, 2])

    async def fake_send(chat_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        return None

    monkeypatch.setattr(n._bot, "send_message", fake_send)
    cand = TokenCandidate(chain="sol", address="T", source=Source.TRENDING, symbol="X")
    assert await n.send_candidate(cand) == (True, True)
    await n.close()


@pytest.mark.asyncio
async def test_send_all_fail(monkeypatch):
    n = TelegramNotifier("000:fake", [1])

    async def fake_send(chat_id, text, disable_web_page_preview=False, parse_mode=None, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(n._bot, "send_message", fake_send)
    cand = TokenCandidate(chain="sol", address="T", source=Source.TRENDING, symbol="X")
    assert await n.send_candidate(cand) == (False, False)
    await n.close()
