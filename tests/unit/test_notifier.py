from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifier.push import notify_users
from src.scraper.running_biji import RaceEvent

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


@pytest.mark.asyncio
async def test_notify_users_sends_card_to_each_subscriber():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [111, 222]

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch("src.notifier.push.send_event_card", new_callable=AsyncMock) as mock_card,
    ):
        await notify_users(bot=mock_bot, hour=8)

    # 2 users × 2 events = 4 card calls
    assert mock_card.call_count == 4
    chat_ids = {c.args[1] for c in mock_card.call_args_list}
    assert chat_ids == {111, 222}


@pytest.mark.asyncio
async def test_notify_users_sends_footer_message_after_cards():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [111]

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch("src.notifier.push.send_event_card", new_callable=AsyncMock),
    ):
        await notify_users(bot=mock_bot, hour=8)

    # footer send_message for the modify_schedule button
    mock_bot.send_message.assert_called_once()
    call = mock_bot.send_message.call_args
    assert call.kwargs["chat_id"] == 111
    markup = call.kwargs.get("reply_markup")
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "modify_schedule" for btn in buttons)


@pytest.mark.asyncio
async def test_notify_users_skips_send_when_no_open_events():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [111]

    with (
        patch("src.notifier.push.fetch_events", return_value=[]),
        patch("src.notifier.push.filter_open_events", return_value=[]),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch("src.notifier.push.send_event_card", new_callable=AsyncMock) as mock_card,
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_card.assert_not_called()
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
        patch("src.notifier.push.send_event_card", new_callable=AsyncMock) as mock_card,
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_card.assert_not_called()
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_queries_correct_hour():
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
