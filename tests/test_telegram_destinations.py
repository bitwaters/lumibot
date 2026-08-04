from lumibot.config import Settings


def test_push_chat_ids_merges_control_and_groups(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "111,222")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_IDS", "-100333,-100333,111")
    s = Settings(_env_file=None)
    assert s.chat_ids() == [111, 222]
    assert s.group_chat_ids() == [-100333, -100333, 111]
    # Dedup while preserving order: control first, then new groups.
    assert s.push_chat_ids() == [111, 222, -100333]


def test_group_chat_ids_optional(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "111")
    monkeypatch.delenv("TELEGRAM_GROUP_CHAT_IDS", raising=False)
    s = Settings(_env_file=None)
    assert s.group_chat_ids() == []
    assert s.push_chat_ids() == [111]


def test_invalid_group_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "111")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_IDS", "abc")
    s = Settings(_env_file=None)
    try:
        s.group_chat_ids()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "TELEGRAM_GROUP_CHAT_IDS" in str(exc)
