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
        city="台北市",
    ),
    RaceEvent(
        name="高雄路跑",
        race_date=date(2026, 12, 6),
        location="高雄市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=22222",
        reg_start=date(2026, 6, 5),
        reg_end=date(2026, 9, 15),
        city="高雄市",
    ),
]

_USERS_ALL = [
    {"user_id": 111, "preferred_city": "all"},
    {"user_id": 222, "preferred_city": "all"},
]


@pytest.mark.asyncio
async def test_notify_users_sends_carousel_to_each_subscriber():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = _USERS_ALL

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch(
            "src.notifier.push.send_carousel_start", new_callable=AsyncMock
        ) as mock_carousel,
    ):
        await notify_users(bot=mock_bot, hour=8)

    assert mock_carousel.call_count == 2
    chat_ids = {c.args[1] for c in mock_carousel.call_args_list}
    assert chat_ids == {111, 222}


@pytest.mark.asyncio
async def test_notify_users_sends_footer_after_carousel():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [
        {"user_id": 111, "preferred_city": "all"}
    ]

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch("src.notifier.push.send_carousel_start", new_callable=AsyncMock),
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_bot.send_message.assert_called_once()
    call = mock_bot.send_message.call_args
    markup = call.kwargs.get("reply_markup")
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "open_settings" for btn in buttons)


@pytest.mark.asyncio
async def test_notify_users_filters_events_by_city():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [
        {"user_id": 111, "preferred_city": "台北市"},
        {"user_id": 222, "preferred_city": "高雄市"},
    ]

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch(
            "src.notifier.push.send_carousel_start", new_callable=AsyncMock
        ) as mock_carousel,
    ):
        await notify_users(bot=mock_bot, hour=8)

    assert mock_carousel.call_count == 2
    call_111 = next(c for c in mock_carousel.call_args_list if c.args[1] == 111)
    assert all(e.city == "台北市" for e in call_111.args[2])
    call_222 = next(c for c in mock_carousel.call_args_list if c.args[1] == 222)
    assert all(e.city == "高雄市" for e in call_222.args[2])


@pytest.mark.asyncio
async def test_notify_users_skips_user_when_no_city_events():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [
        {"user_id": 111, "preferred_city": "嘉義市"}
    ]

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch(
            "src.notifier.push.send_carousel_start", new_callable=AsyncMock
        ) as mock_carousel,
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_carousel.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_skips_when_no_open_events():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = _USERS_ALL

    with (
        patch("src.notifier.push.fetch_events", return_value=[]),
        patch("src.notifier.push.filter_open_events", return_value=[]),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch(
            "src.notifier.push.send_carousel_start", new_callable=AsyncMock
        ) as mock_carousel,
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_carousel.assert_not_called()
    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_skips_when_no_subscribers():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = []

    with (
        patch("src.notifier.push.fetch_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch(
            "src.notifier.push.send_carousel_start", new_callable=AsyncMock
        ) as mock_carousel,
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_carousel.assert_not_called()


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
