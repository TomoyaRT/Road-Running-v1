from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.bot.handlers import (
    build_hour_keyboard,
    build_slot_keyboard,
    handle_text_message,
    hour_callback,
    modify_schedule_callback,
    slot_callback,
    start_command,
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
async def test_slot_callback_morning_shows_hour_buttons(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "slot:morning"
    await slot_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.edit_message_text.assert_called_once()
    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)
    all_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert all(d.startswith("hour:") for d in all_data)


@pytest.mark.asyncio
async def test_slot_callback_shows_hours_in_selected_range(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "slot:morning"
    await slot_callback(mock_callback_update, mock_context)

    call = mock_callback_update.callback_query.edit_message_text.call_args
    markup = call.kwargs.get("reply_markup")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert all(5 <= h <= 11 for h in hours)


# ── hour_callback ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hour_callback_saves_subscription(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "hour:8"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await hour_callback(mock_callback_update, mock_context)

    mock_db.subscribe.assert_called_once_with(
        user_id=mock_callback_update.effective_user.id, notification_hour=8
    )


@pytest.mark.asyncio
async def test_hour_callback_confirms_with_hour(mock_callback_update, mock_context):
    mock_callback_update.callback_query.data = "hour:20"
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await hour_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "20:00" in text
    assert "設定完成" in text


# ── modify_schedule_callback ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_modify_schedule_callback_sends_slot_keyboard(
    mock_callback_update, mock_context
):
    mock_callback_update.callback_query.data = "modify_schedule"
    mock_context.bot = AsyncMock()

    await modify_schedule_callback(mock_callback_update, mock_context)

    mock_context.bot.send_message.assert_called_once()
    call = mock_context.bot.send_message.call_args
    markup = call.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)


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
async def test_handle_text_open_events_sends_cards(mock_update, mock_context):
    mock_update.message.text = "查詢可報名活動"
    mock_context.bot = AsyncMock()

    with (
        patch("src.bot.handlers.fetch_events", return_value=_SAMPLE_EVENTS),
        patch("src.bot.handlers.filter_open_events", return_value=_SAMPLE_EVENTS),
        patch("src.bot.handlers.send_event_card", new_callable=AsyncMock) as mock_card,
    ):
        await handle_text_message(mock_update, mock_context)

    mock_card.assert_called_once()


@pytest.mark.asyncio
async def test_handle_text_open_events_no_results(mock_update, mock_context):
    mock_update.message.text = "查詢可報名活動"

    with (
        patch("src.bot.handlers.fetch_events", return_value=[]),
        patch("src.bot.handlers.filter_open_events", return_value=[]),
    ):
        await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    text = mock_update.message.reply_text.call_args.args[0]
    assert "沒有" in text or "目前" in text


@pytest.mark.asyncio
async def test_handle_text_upcoming_events_sends_cards(mock_update, mock_context):
    mock_update.message.text = "即將開放活動"
    mock_context.bot = AsyncMock()

    upcoming = [
        RaceEvent(
            name="台中賽",
            race_date=date(2026, 12, 1),
            location="台中市",
            url="https://running.biji.co/index.php?q=competition&act=info&cid=22222",
            reg_start=date(2026, 7, 10),
            reg_end=date(2026, 9, 30),
        )
    ]
    with (
        patch("src.bot.handlers.fetch_events", return_value=upcoming),
        patch("src.bot.handlers.filter_upcoming_events", return_value=upcoming),
        patch("src.bot.handlers.send_event_card", new_callable=AsyncMock) as mock_card,
    ):
        await handle_text_message(mock_update, mock_context)

    mock_card.assert_called_once()


@pytest.mark.asyncio
async def test_handle_text_modify_schedule_sends_slot_keyboard(
    mock_update, mock_context
):
    mock_update.message.text = "修改推播時間"
    await handle_text_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(markup, InlineKeyboardMarkup)


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


def test_build_hour_keyboard_morning_has_correct_range():
    markup = build_hour_keyboard("morning")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == set(range(5, 12))


def test_build_hour_keyboard_evening_has_correct_range():
    markup = build_hour_keyboard("evening")
    hours = [
        int(btn.callback_data.split(":")[1])
        for row in markup.inline_keyboard
        for btn in row
    ]
    assert set(hours) == set(range(18, 24))


def test_build_slot_keyboard_has_three_slots():
    markup = build_slot_keyboard()
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 3
    assert all(btn.callback_data.startswith("slot:") for btn in buttons)
