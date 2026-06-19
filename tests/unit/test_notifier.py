from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.notifier.push import build_notification_text, notify_users

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
    chat_ids = {call.kwargs["chat_id"] for call in call_args_list}
    assert chat_ids == {111, 222}


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
