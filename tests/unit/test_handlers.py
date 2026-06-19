from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.bot.handlers import (
    build_city_keyboard,
    build_city_only_keyboard,
    build_hour_keyboard,
    build_settings_keyboard,
    build_slot_keyboard,
    city_callback,
    city_only_callback,
    handle_text_message,
    hour_callback,
    nav_callback,
    open_settings_callback,
    settings_city_callback,
    settings_time_callback,
    slot_callback,
    start_command,
    unsubscribe_btn_callback,
    unsubscribe_command,
)
from src.scraper.running_biji import RaceEvent

# ── /start ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_command_sends_welcome_with_persistent_keyboard(
    mock_update, mock_context
):
    await start_command(mock_update, mock_context)

    assert mock_update.message.reply_text.call_count == 2
    first_call = mock_update.message.reply_text.call_args_list[0]
    text = first_call.args[0] if first_call.args else first_call.kwargs["text"]
    markup = first_call.kwargs.get("reply_markup")
    assert "歡迎" in text
    assert isinstance(markup, ReplyKeyboardMarkup)


@pytest.mark.asyncio
async def test_start_command_sends_slot_selection_keyboard(mock_update, mock_context):
    await start_command(mock_update, mock_context)

    second_call = mock_update.message.reply_text.call_args_list[1]
    markup = second_call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("slot:") for d in all_data)


# ── slot_callback ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slot_callback_shows_hour_buttons(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "slot:s1"
    await slot_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_text.assert_called_once()
    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("hour:") for d in all_data)


@pytest.mark.asyncio
async def test_slot_callback_shows_hours_in_s1_range(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "slot:s1"
    await slot_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {5, 6, 7, 8, 9, 10}


@pytest.mark.asyncio
async def test_slot_callback_shows_hours_in_s4_range(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "slot:s4"
    await slot_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {20, 21, 22, 23}


# ── hour_callback ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hour_callback_shows_city_selection_keyboard(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "hour:9"
    await hour_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_text.assert_called_once()
    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("city:9:") for d in all_data)


@pytest.mark.asyncio
async def test_hour_callback_includes_selected_hour_in_city_callbacks(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "hour:20"
    await hour_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("city:20:") for d in all_data)


@pytest.mark.asyncio
async def test_hour_callback_does_not_save_subscription(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "hour:8"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await hour_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_not_called()


# ── city_callback ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_city_callback_saves_subscription(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "city:9:台北市"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id,
        notification_hour=9,
        preferred_city="台北市",
    )


@pytest.mark.asyncio
async def test_city_callback_saves_all_city(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "city:14:all"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id,
        notification_hour=14,
        preferred_city="all",
    )


@pytest.mark.asyncio
async def test_city_callback_shows_confirmation(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "city:9:台北市"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "09:00" in text
    assert "台北市" in text
    assert "設定完成" in text


# ── open_settings_callback ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_settings_callback_shows_settings_menu(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "open_settings"
    await open_settings_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_text.assert_called_once()
    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "settings_time" in all_data
    assert "settings_city" in all_data
    assert "unsubscribe_btn" in all_data


# ── settings_time_callback ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_time_callback_shows_slot_keyboard(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "settings_time"
    await settings_time_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("slot:") for d in all_data)


# ── settings_city_callback ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_city_callback_shows_city_only_keyboard(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "settings_city"
    await settings_city_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any(d.startswith("city_only:") for d in all_data)


# ── city_only_callback ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_city_only_callback_calls_update_city(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "city_only:台中市"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_only_callback(mock_callback_update, mock_context)

    mock_db.update_city.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id,
        preferred_city="台中市",
    )


@pytest.mark.asyncio
async def test_city_only_callback_does_not_touch_hour(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "city_only:all"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_only_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_city_only_callback_shows_confirmation(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "city_only:高雄市"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await city_only_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "高雄市" in text


# ── unsubscribe_btn_callback ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_btn_callback_deletes_user(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "unsubscribe_btn"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await unsubscribe_btn_callback(mock_callback_update, mock_context)

    mock_db.unsubscribe.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id
    )


@pytest.mark.asyncio
async def test_unsubscribe_btn_callback_shows_confirmation(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "unsubscribe_btn"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await unsubscribe_btn_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "取消" in text


# ── nav_callback ──────────────────────────────────────────────────────────────

_SAMPLE_EVENTS_NAV = [
    RaceEvent(
        name=f"活動{i}",
        race_date=date(2026, 11, i + 1),
        location="台北市",
        url=f"https://running.biji.co/index.php?q=competition&act=info&cid={i}",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
        city="台北市",
    )
    for i in range(3)
]


@pytest.mark.asyncio
async def test_nav_callback_edits_message_for_open_events(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "nav:o:1:all"

    with (
        patch("src.bot.handlers.fetch_events", return_value=_SAMPLE_EVENTS_NAV),
        patch("src.bot.handlers.filter_open_events", return_value=_SAMPLE_EVENTS_NAV),
        patch(
            "src.bot.handlers.filter_events_by_city", return_value=_SAMPLE_EVENTS_NAV
        ),
        patch(
            "src.bot.handlers.fetch_official_url_async",
            new=AsyncMock(return_value=None),
        ),
    ):
        await nav_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_media.assert_called_once()


@pytest.mark.asyncio
async def test_nav_callback_shows_correct_event_index(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "nav:o:1:all"

    with (
        patch("src.bot.handlers.fetch_events", return_value=_SAMPLE_EVENTS_NAV),
        patch("src.bot.handlers.filter_open_events", return_value=_SAMPLE_EVENTS_NAV),
        patch(
            "src.bot.handlers.filter_events_by_city", return_value=_SAMPLE_EVENTS_NAV
        ),
        patch(
            "src.bot.handlers.fetch_official_url_async",
            new=AsyncMock(return_value=None),
        ),
    ):
        await nav_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_media.call_args
    media = call.kwargs.get("media") or call.args[0]
    assert "活動1" in media.caption
    assert "2 / 3" in media.caption


@pytest.mark.asyncio
async def test_nav_callback_uses_official_url_when_available(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "nav:o:0:all"
    official = "https://official-reg.example.com"

    with (
        patch("src.bot.handlers.fetch_events", return_value=_SAMPLE_EVENTS_NAV),
        patch("src.bot.handlers.filter_open_events", return_value=_SAMPLE_EVENTS_NAV),
        patch(
            "src.bot.handlers.filter_events_by_city", return_value=_SAMPLE_EVENTS_NAV
        ),
        patch(
            "src.bot.handlers.fetch_official_url_async",
            new=AsyncMock(return_value=official),
        ),
    ):
        await nav_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_media.call_args
    markup = call.kwargs.get("reply_markup")
    reg_buttons = [btn for row in markup.inline_keyboard for btn in row if btn.url]
    assert reg_buttons[0].url == official


# ── handle_text_message ────────────────────────────────────────────────────────

_SAMPLE_EVENTS = [
    RaceEvent(
        name="台北馬拉松",
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=11111",
        reg_start=date(2026, 6, 1),
        reg_end=date(2026, 8, 31),
    )
]


@pytest.mark.asyncio
async def test_handle_text_open_events_sends_webapp_button(mock_update, mock_context):
    mock_update.message.text = "查詢可報名活動"

    with patch.dict("os.environ", {"GCP_CLOUD_RUN_URL": "https://test.run.app"}):
        await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(
        btn.web_app is not None and "type=open" in btn.web_app.url for btn in buttons
    )


@pytest.mark.asyncio
async def test_handle_text_upcoming_events_sends_webapp_button(
    mock_update, mock_context
):
    mock_update.message.text = "即將開放活動"

    with patch.dict("os.environ", {"GCP_CLOUD_RUN_URL": "https://test.run.app"}):
        await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(
        btn.web_app is not None and "type=upcoming" in btn.web_app.url
        for btn in buttons
    )


@pytest.mark.asyncio
async def test_handle_text_settings_shows_settings_keyboard(mock_update, mock_context):
    mock_update.message.text = "設定"
    await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "settings_time" in all_data
    assert "settings_city" in all_data
    assert "unsubscribe_btn" in all_data


# ── /unsubscribe ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_deletes_user(mock_update, mock_context):
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await unsubscribe_command(mock_update, mock_context)

    mock_db.unsubscribe.assert_called_once_with(user_id=mock_update.effective_user.id)
    text = mock_update.message.reply_text.call_args.args[0]
    assert "取消" in text


# ── build_hour_keyboard ────────────────────────────────────────────────────────


def test_build_hour_keyboard_s1_has_correct_range():
    markup = build_hour_keyboard("s1")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {5, 6, 7, 8, 9, 10}


def test_build_hour_keyboard_s2_has_correct_range():
    markup = build_hour_keyboard("s2")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {10, 11, 12, 13, 14, 15}


def test_build_hour_keyboard_s3_has_correct_range():
    markup = build_hour_keyboard("s3")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {15, 16, 17, 18, 19, 20}


def test_build_hour_keyboard_s4_has_correct_range():
    markup = build_hour_keyboard("s4")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == {20, 21, 22, 23}


def test_build_hour_keyboard_uses_three_per_row():
    markup = build_hour_keyboard("s1")
    for row in markup.inline_keyboard:
        assert len(row) <= 3


# ── build_slot_keyboard ────────────────────────────────────────────────────────


def test_build_slot_keyboard_has_four_slots():
    markup = build_slot_keyboard()
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 4
    assert all(btn.callback_data.startswith("slot:") for btn in buttons)


def test_build_slot_keyboard_has_two_per_row():
    markup = build_slot_keyboard()
    for row in markup.inline_keyboard:
        assert len(row) == 2


def test_build_slot_keyboard_covers_all_slots():
    markup = build_slot_keyboard()
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "slot:s1" in all_data
    assert "slot:s2" in all_data
    assert "slot:s3" in all_data
    assert "slot:s4" in all_data


# ── build_city_keyboard ────────────────────────────────────────────────────────


def test_build_city_keyboard_embeds_hour_in_callback_data():
    markup = build_city_keyboard(hour=9)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("city:9:") for d in all_data)


def test_build_city_keyboard_includes_all_taiwan_option():
    markup = build_city_keyboard(hour=9)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "city:9:all" in all_data


def test_build_city_keyboard_has_multiple_cities():
    markup = build_city_keyboard(hour=9)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) >= 3


# ── build_settings_keyboard ───────────────────────────────────────────────────


def test_build_settings_keyboard_has_time_city_and_unsubscribe():
    markup = build_settings_keyboard()
    all_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "settings_time" in all_data
    assert "settings_city" in all_data
    assert "unsubscribe_btn" in all_data


# ── build_city_only_keyboard ──────────────────────────────────────────────────


def test_build_city_only_keyboard_uses_city_only_prefix():
    markup = build_city_only_keyboard()
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("city_only:") for d in all_data)


def test_build_city_only_keyboard_includes_all_option():
    markup = build_city_only_keyboard()
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "city_only:all" in all_data
