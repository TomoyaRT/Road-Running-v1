from __future__ import annotations

import pytest
from src.bot.handlers import start_command


@pytest.mark.asyncio
async def test_start_command_replies_with_welcome(mock_update, mock_context):
    """start_command 應回覆歡迎訊息。"""
    await start_command(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_once()
    call_kwargs = mock_update.message.reply_text.call_args
    text = (
        call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("text", "")
    )
    assert "歡迎" in text


@pytest.mark.asyncio
async def test_start_command_includes_inline_keyboard(mock_update, mock_context):
    """start_command 應附帶 InlineKeyboard 按鈕。"""
    from telegram import InlineKeyboardMarkup

    await start_command(mock_update, mock_context)

    call_kwargs = mock_update.message.reply_text.call_args
    reply_markup = call_kwargs.kwargs.get("reply_markup")
    assert reply_markup is not None
    assert isinstance(reply_markup, InlineKeyboardMarkup)


@pytest.mark.asyncio
async def test_start_command_keyboard_has_upcoming_button(mock_update, mock_context):
    """InlineKeyboard 應包含「即將開啟的活動」按鈕，callback_data 為 'upcoming_events'。"""
    await start_command(mock_update, mock_context)

    call_kwargs = mock_update.message.reply_text.call_args
    reply_markup = call_kwargs.kwargs.get("reply_markup")
    buttons = [btn for row in reply_markup.inline_keyboard for btn in row]
    callback_datas = [btn.callback_data for btn in buttons]
    assert "upcoming_events" in callback_datas
