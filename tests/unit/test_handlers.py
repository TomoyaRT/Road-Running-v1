from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup

from src.bot.handlers import (
    start_command,
    subscribe_command,
    unsubscribe_command,
    upcoming_events_callback,
)
from src.scraper.running_biji import RaceEvent

# ── /start command ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_command_replies_with_welcome(mock_update, mock_context):
    await start_command(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    call_kwargs = mock_update.message.reply_text.call_args
    text = (
        call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("text", "")
    )
    assert "歡迎" in text


@pytest.mark.asyncio
async def test_start_command_includes_inline_keyboard(mock_update, mock_context):
    await start_command(mock_update, mock_context)

    reply_markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    assert isinstance(reply_markup, InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_start_command_keyboard_has_upcoming_button(mock_update, mock_context):
    await start_command(mock_update, mock_context)

    reply_markup = mock_update.message.reply_text.call_args.kwargs.get("reply_markup")
    callback_datas = [
        btn.callback_data for row in reply_markup.inline_keyboard for btn in row
    ]
    assert "upcoming_events" in callback_datas


# ── /subscribe command ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_saves_user_with_valid_hour(mock_update, mock_context):
    mock_update.message.text = "/subscribe 8"
    mock_context.args = ["8"]
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await subscribe_command(mock_update, mock_context)

    mock_db.subscribe.assert_called_once_with(
        user_id=mock_update.effective_user.id, notification_hour=8
    )
    mock_update.message.reply_text.assert_called_once()
    text = mock_update.message.reply_text.call_args.args[0]
    assert "訂閱" in text or "8" in text


@pytest.mark.asyncio
async def test_subscribe_rejects_invalid_hour(mock_update, mock_context):
    mock_context.args = ["25"]
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await subscribe_command(mock_update, mock_context)

    mock_db.subscribe.assert_not_called()
    text = mock_update.message.reply_text.call_args.args[0]
    assert "0" in text and "23" in text


@pytest.mark.asyncio
async def test_subscribe_rejects_missing_argument(mock_update, mock_context):
    mock_context.args = []
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await subscribe_command(mock_update, mock_context)

    mock_db.subscribe.assert_not_called()
    mock_update.message.reply_text.assert_called_once()


# ── /unsubscribe command ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_deletes_user(mock_update, mock_context):
    mock_db = MagicMock()

    with patch("src.bot.handlers.get_db", return_value=mock_db):
        await unsubscribe_command(mock_update, mock_context)

    mock_db.unsubscribe.assert_called_once_with(user_id=mock_update.effective_user.id)
    mock_update.message.reply_text.assert_called_once()
    text = mock_update.message.reply_text.call_args.args[0]
    assert "取消" in text


# ── upcoming_events callback ──────────────────────────────────────────────────

_SAMPLE_EVENTS = [
    RaceEvent(
        name="台北馬拉松",
        race_date=date(2026, 11, 15),
        location="台北市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=11111",
        reg_start=date(2026, 7, 10),
        reg_end=date(2026, 9, 30),
    ),
    RaceEvent(
        name="台中賽",
        race_date=date(2026, 12, 1),
        location="台中市",
        url="https://running.biji.co/index.php?q=competition&act=info&cid=22222",
        reg_start=date(2026, 8, 1),
        reg_end=date(2026, 10, 31),
    ),
]


@pytest.mark.asyncio
async def test_upcoming_events_callback_answers_query(
    mock_callback_update, mock_context
):
    with patch("src.bot.handlers.fetch_events", return_value=_SAMPLE_EVENTS):
        await upcoming_events_callback(mock_callback_update, mock_context)

    mock_callback_update.callback_query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_upcoming_events_callback_sends_event_list(
    mock_callback_update, mock_context
):
    # 固定 today=2026-07-05，使兩筆活動（開報 07/10, 08/01）均在 30 天內
    with (
        patch("src.bot.handlers.date") as mock_date,
        patch("src.bot.handlers.fetch_events", return_value=_SAMPLE_EVENTS),
    ):
        mock_date.today.return_value = date(2026, 7, 5)
        await upcoming_events_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "台北馬拉松" in text
    assert "台中賽" in text


@pytest.mark.asyncio
async def test_upcoming_events_callback_shows_no_events_message(
    mock_callback_update, mock_context
):
    with patch("src.bot.handlers.fetch_events", return_value=[]):
        await upcoming_events_callback(mock_callback_update, mock_context)

    text = mock_callback_update.callback_query.edit_message_text.call_args.args[0]
    assert "目前" in text or "沒有" in text or "查無" in text
