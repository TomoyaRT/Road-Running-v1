from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifier.push import _chunk_text, build_notification_text, notify_users
from src.scraper.running_biji import RaceEvent

# ── fixtures ──────────────────────────────────────────────────────────────────

_OPEN_EVENTS = [
    RaceEvent(
        name="台北馬拉松",
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=11111",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
    ),
    RaceEvent(
        name="高雄路跑",
        race_date=date(2026, 12, 6),
        location="高雄市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=22222",
        reg_start=date(2026, 6, 5),
        reg_end=date(2026, 9, 15),
    ),
]


def _make_events(n: int) -> list[RaceEvent]:
    return [
        RaceEvent(
            name=f"台北路跑活動第{i:03d}屆全程馬拉松",
            race_date=date(2026, 11, 15),
            location="台北市大安區",
            url=f"https://running.biji.co/index.php?q=competition&act=info&cid={10000 + i}",
            reg_start=date(2026, 6, 1),
            reg_end=date(2026, 8, 31),
        )
        for i in range(n)
    ]


# ── build_notification_text ────────────────────────────────────────────────────


def test_build_notification_text_contains_all_event_names():
    text = build_notification_text(_OPEN_EVENTS)
    assert "台北馬拉松" in text
    assert "高雄路跑" in text


def test_build_notification_text_contains_location_and_url():
    text = build_notification_text(_OPEN_EVENTS)
    assert "台北市" in text
    assert "cid=11111" in text


def test_build_notification_text_empty_returns_no_events_message():
    text = build_notification_text([])
    assert "今日" in text or "沒有" in text or "目前" in text


def test_build_notification_text_events_separated_by_double_newline():
    text = build_notification_text(_OPEN_EVENTS)
    blocks = text.split("\n\n")
    assert len(blocks) >= 3
    assert "台北馬拉松" in blocks[1]
    assert "高雄路跑" in blocks[2]


# ── _chunk_text ───────────────────────────────────────────────────────────────


def test_chunk_text_short_text_returns_single_chunk():
    chunks = _chunk_text("short text")
    assert chunks == ["short text"]


def test_chunk_text_each_chunk_within_limit():
    chunks = _chunk_text("\n\n".join(["a" * 100] * 50))
    for chunk in chunks:
        assert len(chunk) <= 4096


def test_chunk_text_with_real_notification_output_stays_within_limit():
    events = _make_events(50)
    text = build_notification_text(events)
    assert len(text) > 4096
    chunks = _chunk_text(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4096


def test_chunk_text_oversized_single_block_stays_within_limit():
    big_block = "\n".join(["x" * 100] * 50)
    assert len(big_block) > 4096
    chunks = _chunk_text(big_block)
    for chunk in chunks:
        assert len(chunk) <= 4096


def test_chunk_text_oversized_single_line_stays_within_limit():
    # 單一行本身超過 4096（極端情況），需截斷
    single_long_line = "y" * 5000
    chunks = _chunk_text(single_long_line)
    for chunk in chunks:
        assert len(chunk) <= 4096


# ── notify_users ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_users_sends_message_to_each_subscriber():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [111, 222]

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    assert mock_bot.send_message.call_count == 2
    call_args_list = mock_bot.send_message.call_args_list
    chat_ids = {c.kwargs["chat_id"] for c in call_args_list}
    assert chat_ids == {111, 222}


@pytest.mark.asyncio
async def test_notify_users_sends_multiple_chunks_for_long_content():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [111]
    many_events = _make_events(50)

    with (
        patch("src.notifier.push.fetch_events", return_value=many_events),
        patch("src.notifier.push.filter_open_events", return_value=many_events),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    assert mock_bot.send_message.call_count > 1
    for c in mock_bot.send_message.call_args_list:
        assert len(c.kwargs["text"]) <= 4096


@pytest.mark.asyncio
async def test_notify_users_skips_send_when_no_open_events():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [111]

    with (
        patch("src.notifier.push.fetch_events", return_value=[]),
        patch("src.notifier.push.filter_open_events", return_value=[]),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_skips_send_when_no_subscribers():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = []

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_queries_correct_hour(mock_context):
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = []

    with (
        patch("src.notifier.push.fetch_events", return_value=[]),
        patch("src.notifier.push.filter_open_events", return_value=[]),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=20)

    mock_db.get_users_for_hour.assert_called_once_with(hour=20)
