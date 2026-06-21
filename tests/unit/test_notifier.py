from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest

from src.notifier.push import notify_users
from src.scraper.running_biji import RaceEvent

# ── tw_today 整合驗證 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_users_uses_tw_today_for_date_filtering():
    """notify_users 必須用 tw_today() 而非 date.today() 來過濾活動。"""
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [
        {"user_id": 111, "preferred_city": "all"}
    ]
    mock_db.get_events.return_value = []

    with (
        patch("src.notifier.push.get_db", return_value=mock_db),
        patch("src.notifier.push.filter_open_events", return_value=[]),
        patch("src.notifier.push.tw_today") as mock_tw_today,
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_tw_today.assert_called_once()


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


def _all_buttons(markup):
    return [btn for row in markup.inline_keyboard for btn in row]


@pytest.mark.asyncio
async def test_notify_users_sends_miniapp_to_each_subscriber():
    """推播改用 mini app：每位訂閱者收到一則含 web_app 按鈕的訊息。"""
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = _USERS_ALL
    mock_db.get_events.return_value = _OPEN_EVENTS

    with (
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    assert mock_bot.send_message.call_count == 2
    chat_ids = {c.kwargs["chat_id"] for c in mock_bot.send_message.call_args_list}
    assert chat_ids == {111, 222}
    for c in mock_bot.send_message.call_args_list:
        buttons = _all_buttons(c.kwargs["reply_markup"])
        assert any(btn.web_app is not None for btn in buttons)


@pytest.mark.asyncio
async def test_notify_users_miniapp_message_has_no_settings_button():
    """推播訊息不應包含 inline「設定」按鈕（設定入口保留在常駐鍵盤）。"""
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [
        {"user_id": 111, "preferred_city": "all"}
    ]
    mock_db.get_events.return_value = _OPEN_EVENTS

    with (
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_bot.send_message.assert_called_once()
    buttons = _all_buttons(mock_bot.send_message.call_args.kwargs["reply_markup"])
    assert any(btn.web_app is not None for btn in buttons)
    assert not any(
        getattr(btn, "callback_data", None) == "open_settings" for btn in buttons
    )


@pytest.mark.asyncio
async def test_notify_users_filters_events_by_city():
    """城市偏好仍決定是否推播：兩位不同城市、各有活動者都各收到一則。"""
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [
        {"user_id": 111, "preferred_city": "台北市"},
        {"user_id": 222, "preferred_city": "高雄市"},
    ]
    mock_db.get_events.return_value = _OPEN_EVENTS

    with (
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    assert mock_bot.send_message.call_count == 2
    by_uid = {c.kwargs["chat_id"]: c for c in mock_bot.send_message.call_args_list}
    assert set(by_uid) == {111, 222}
    # mini app URL 帶上各自的城市偏好（URL-encoded）
    url_111 = _all_buttons(by_uid[111].kwargs["reply_markup"])[0].web_app.url
    url_222 = _all_buttons(by_uid[222].kwargs["reply_markup"])[0].web_app.url
    assert quote("台北市") in url_111
    assert quote("高雄市") in url_222


@pytest.mark.asyncio
async def test_notify_users_skips_user_when_no_city_events():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = [
        {"user_id": 111, "preferred_city": "嘉義市"}
    ]
    mock_db.get_events.return_value = _OPEN_EVENTS

    with (
        patch("src.notifier.push.filter_open_events", return_value=_OPEN_EVENTS),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_skips_when_no_open_events():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = _USERS_ALL
    mock_db.get_events.return_value = []

    with (
        patch("src.notifier.push.filter_open_events", return_value=[]),
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_skips_when_no_subscribers():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = []

    with (
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=8)

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_users_queries_correct_hour():
    mock_bot = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_users_for_hour.return_value = []

    with (
        patch("src.notifier.push.get_db", return_value=mock_db),
    ):
        await notify_users(bot=mock_bot, hour=20)

    mock_db.get_users_for_hour.assert_called_once_with(hour=20)
