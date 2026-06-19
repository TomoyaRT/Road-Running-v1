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

from src.bot.cards import (
    build_nav_markup,
    format_carousel_text,
    send_carousel_start,
)
from src.db.firestore_client import FirestoreClient
from src.scraper.running_biji import (
    fetch_events,
    fetch_official_url_async,
    filter_events_by_city,
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

_CITY_OPTIONS: list[tuple[str, str]] = [
    ("台北市", "台北市"),
    ("新北市", "新北市"),
    ("桃園市", "桃園市"),
    ("台中市", "台中市"),
    ("台南市", "台南市"),
    ("高雄市", "高雄市"),
    ("嘉義市", "嘉義市"),
    ("新竹市", "新竹市"),
    ("全部台灣", "all"),
]

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
_ASK_CITY_TEXT = "請選擇你希望收到哪個地區的路跑活動通知："
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


def build_city_keyboard(hour: int) -> InlineKeyboardMarkup:
    """建立城市選擇鍵盤，callback_data 帶入選定的 hour。"""
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(_CITY_OPTIONS), 3):
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"city:{hour}:{key}")
                for label, key in _CITY_OPTIONS[i : i + 3]
            ]
        )
    return InlineKeyboardMarkup(rows)


def _city_display(city: str) -> str:
    return "全台灣" if city == "all" else city


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
    """使用者選擇推播時間後，進入城市選擇步驟（尚未儲存訂閱）。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    await query.answer()
    hour = int(query.data.split(":", 1)[1])
    await query.edit_message_text(
        f"你選擇了每天 {hour:02d}:00 接收通知。\n\n{_ASK_CITY_TEXT}",
        reply_markup=build_city_keyboard(hour),
    )


async def city_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """使用者選擇城市後，儲存訂閱並顯示確認訊息。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_user is not None
    await query.answer()

    # callback_data: "city:{hour}:{city}"
    parts = query.data.split(":", 2)
    hour = int(parts[1])
    city = parts[2]

    db = get_db()
    db.subscribe(
        user_id=update.effective_user.id, notification_hour=hour, preferred_city=city
    )

    city_label = _city_display(city)
    await query.edit_message_text(
        f"設定完成！每天 {hour:02d}:00 推播 {city_label} 可報名路跑活動給你。"
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


async def nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """輪播導航：更新訊息顯示上一張 / 下一張活動卡片。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    await query.answer()

    # callback_data: "nav:{type}:{index}:{city}"
    parts = query.data.split(":", 3)
    event_type = parts[1]  # "o" (open) or "u" (upcoming)
    index = int(parts[2])
    city = parts[3]

    events = fetch_events()
    today = date.today()
    if event_type == "o":
        filtered = filter_open_events(events, today)
    else:
        filtered = filter_upcoming_events(events, today)

    city_events = filter_events_by_city(filtered, city)
    total = len(city_events)

    if not city_events or index < 0 or index >= total:
        return

    event = city_events[index]
    official_url = await fetch_official_url_async(event.url) or event.url
    text = format_carousel_text(event, index, total)
    markup = build_nav_markup(event_type, index, total, city, official_url)
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=markup)


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
    await send_carousel_start(
        context.bot, update.effective_chat.id, open_events, "o", "all"
    )


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
    await send_carousel_start(
        context.bot, update.effective_chat.id, upcoming, "u", "all"
    )


async def unsubscribe_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    assert update.effective_user is not None
    db = get_db()
    db.unsubscribe(user_id=update.effective_user.id)
    await update.message.reply_text("已取消訂閱，不再推播路跑通知。")
