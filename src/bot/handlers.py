from __future__ import annotations

import logging
import os
from datetime import date

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from src.bot.cards import send_event_card
from src.db.firestore_client import FirestoreClient
from src.scraper.running_biji import (
    fetch_events,
    filter_open_events,
    filter_upcoming_events,
)

logger = logging.getLogger(__name__)

# 各時段不含右端點，避免邊界重疊
_SLOT_HOURS: dict[str, list[int]] = {
    "morning": list(range(5, 12)),  # 05:00 – 11:00
    "afternoon": list(range(12, 18)),  # 12:00 – 17:00
    "evening": list(range(18, 24)),  # 18:00 – 23:00
}

_SLOT_LABELS: dict[str, str] = {
    "morning": "早上 05:00 - 12:00",
    "afternoon": "下午 12:00 - 18:00",
    "evening": "晚上 18:00 - 24:00",
}

PERSISTENT_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("查詢可報名活動"), KeyboardButton("即將開放活動")],
        [KeyboardButton("修改推播時間")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

WELCOME_TEXT = (
    "歡迎加入台灣路跑通知！\n\n"
    "我每天在你指定的時間推播目前可以報名的路跑活動，讓你不錯過任何賽事。\n\n"
    "你也可以隨時用下方按鈕查詢最新活動或修改通知設定。"
)

_ASK_SLOT_TEXT = "請選擇你希望每天收到路跑活動通知的時段："
_NO_OPEN_EVENTS = "目前沒有正在開放報名的路跑活動，請稍後再試。"
_NO_UPCOMING_EVENTS = "目前 30 天內沒有即將開放報名的活動。"


def get_db() -> FirestoreClient:
    return FirestoreClient(project_id=os.environ["GCP_PROJECT_ID"])


def build_slot_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=f"slot:{key}")]
            for key, label in _SLOT_LABELS.items()
        ]
    )


def build_hour_keyboard(slot: str) -> InlineKeyboardMarkup:
    hours = _SLOT_HOURS.get(slot, [])
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(hours), 4):
        rows.append(
            [
                InlineKeyboardButton(f"{h:02d}:00", callback_data=f"hour:{h}")
                for h in hours[i : i + 4]
            ]
        )
    return InlineKeyboardMarkup(rows)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_text(WELCOME_TEXT, reply_markup=PERSISTENT_KEYBOARD)
    await update.message.reply_text(_ASK_SLOT_TEXT, reply_markup=build_slot_keyboard())


async def slot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    await query.answer()
    slot = query.data.split(":", 1)[1]
    label = _SLOT_LABELS.get(slot, slot)
    await query.edit_message_text(
        f"你選擇了「{label}」，請選擇具體的推播時間：",
        reply_markup=build_hour_keyboard(slot),
    )


async def hour_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_user is not None
    await query.answer()
    hour = int(query.data.split(":", 1)[1])
    db = get_db()
    db.subscribe(user_id=update.effective_user.id, notification_hour=hour)
    await query.edit_message_text(
        f"設定完成！每天 {hour:02d}:00 你會收到可報名的路跑活動通知。"
    )


async def modify_schedule_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    assert query is not None
    assert update.effective_chat is not None
    await query.answer()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=_ASK_SLOT_TEXT,
        reply_markup=build_slot_keyboard(),
    )


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    text = update.message.text
    if text == "查詢可報名活動":
        await _handle_open_events(update, context)
    elif text == "即將開放活動":
        await _handle_upcoming_events(update, context)
    elif text == "修改推播時間":
        await update.message.reply_text(
            _ASK_SLOT_TEXT, reply_markup=build_slot_keyboard()
        )


async def _handle_open_events(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    assert update.effective_chat is not None
    events = fetch_events()
    open_events = filter_open_events(events, date.today())
    if not open_events:
        await update.message.reply_text(_NO_OPEN_EVENTS)
        return
    for event in open_events:
        await send_event_card(context.bot, update.effective_chat.id, event)


async def _handle_upcoming_events(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    assert update.effective_chat is not None
    events = fetch_events()
    upcoming = filter_upcoming_events(events, date.today())
    if not upcoming:
        await update.message.reply_text(_NO_UPCOMING_EVENTS)
        return
    for event in upcoming:
        await send_event_card(context.bot, update.effective_chat.id, event)


async def unsubscribe_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    assert update.effective_user is not None
    db = get_db()
    db.unsubscribe(user_id=update.effective_user.id)
    await update.message.reply_text("已取消訂閱，不再推播路跑通知。")
