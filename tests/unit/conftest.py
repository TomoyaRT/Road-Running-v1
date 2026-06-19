from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, Message, Update, User
from telegram.ext import ContextTypes


@pytest.fixture
def mock_update() -> MagicMock:
    """模擬 Telegram Update 物件，用於所有 handler 的 unit test。"""
    user = User(id=123, first_name="TestUser", is_bot=False, username="testuser")
    chat = Chat(id=123, type="private")

    message = MagicMock(spec=Message)
    message.chat = chat
    message.from_user = user
    message.reply_text = AsyncMock()
    message.reply_html = AsyncMock()

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.effective_message = message
    update.message = message
    update.callback_query = None
    return update


@pytest.fixture
def mock_context() -> MagicMock:
    """模擬 Telegram Context 物件。"""
    ctx = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    ctx.bot = AsyncMock()
    ctx.user_data = {}
    ctx.chat_data = {}
    return ctx


@pytest.fixture
def mock_callback_update() -> MagicMock:
    """模擬 InlineKeyboard 按鈕點擊的 Update 物件。"""
    user = User(id=123, first_name="TestUser", is_bot=False, username="testuser")
    chat = Chat(id=123, type="private")

    callback_query = MagicMock()
    callback_query.from_user = user
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()
    callback_query.message = MagicMock(spec=Message)
    callback_query.message.chat = chat

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.callback_query = callback_query
    update.message = None
    return update
