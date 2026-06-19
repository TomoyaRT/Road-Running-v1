from __future__ import annotations

import logging
import os
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.db.firestore_client import FirestoreClient
from src.scraper.running_biji import fetch_events, filter_upcoming_events

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "歡迎使用台灣路跑通知機器人！🏃\n\n"
    "每日推播可報名的路跑活動。\n"
    "使用 /subscribe <0-23> 訂閱每日通知，例如 /subscribe 8\n"
    "點下方按鈕查詢 30 天內即將開放報名的活動。"
)

NO_EVENTS_TEXT = "目前 30 天內沒有即將開放報名的活動。"
SUBSCRIBE_USAGE_TEXT = "請輸入通知時段（0-23），例如：/subscribe 8"
SUBSCRIBE_INVALID_TEXT = "時段必須介於 0 到 23 之間，例如：/subscribe 8"


def get_db() -> FirestoreClient:
    return FirestoreClient(project_id=os.environ["GCP_PROJECT_ID"])


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


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(SUBSCRIBE_USAGE_TEXT)
        return

    try:
        hour = int(context.args[0])
    except ValueError:
        await update.message.reply_text(SUBSCRIBE_INVALID_TEXT)
        return

    if not 0 <= hour <= 23:
        await update.message.reply_text(SUBSCRIBE_INVALID_TEXT)
        return

    db = get_db()
    db.subscribe(user_id=update.effective_user.id, notification_hour=hour)
    await update.message.reply_text(
        f"已訂閱！每天 {hour:02d}:00 會推播可報名的路跑活動。"
    )


async def unsubscribe_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    db = get_db()
    db.unsubscribe(user_id=update.effective_user.id)
    await update.message.reply_text("已取消訂閱，不再推播路跑通知。")
