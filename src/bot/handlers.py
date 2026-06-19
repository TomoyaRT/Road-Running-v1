from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "歡迎使用台灣路跑通知機器人！🏃\n\n"
    "每日推播可報名的路跑活動。\n"
    "點下方按鈕查詢 30 天內即將開放報名的活動。"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("即將開啟的活動", callback_data="upcoming_events")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(WELCOME_TEXT, reply_markup=reply_markup)
