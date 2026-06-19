from __future__ import annotations

import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.scraper.running_biji import fetch_events, filter_upcoming_events

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "歡迎使用台灣路跑通知機器人！🏃\n\n"
    "每日推播可報名的路跑活動。\n"
    "點下方按鈕查詢 30 天內即將開放報名的活動。"
)

NO_EVENTS_TEXT = "目前 30 天內沒有即將開放報名的活動。"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("即將開啟的活動", callback_data="upcoming_events")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(WELCOME_TEXT, reply_markup=reply_markup)


async def upcoming_events_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    events = fetch_events()
    upcoming = filter_upcoming_events(events, date.today())

    if not upcoming:
        await query.edit_message_text(NO_EVENTS_TEXT)
        return

    lines = ["📅 30 天內即將開放報名的活動：\n"]
    for e in upcoming:
        reg = e.reg_start.strftime("%m/%d") if e.reg_start else "?"
        lines.append(f"• {e.name}（{e.location}）\n  開報：{reg}  {e.url}")
    await query.edit_message_text("\n".join(lines))
