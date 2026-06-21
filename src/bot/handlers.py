from __future__ import annotations

import logging
import os
from urllib.parse import quote

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import ContextTypes

from src.db.firestore_client import FirestoreClient

logger = logging.getLogger(__name__)

# 4 個時段，每段 6 個（最後一段 4 個）
_SLOT_HOURS: dict[str, list[int]] = {
    "s1": list(range(5, 11)),  # 05:00 – 10:00
    "s2": list(range(10, 16)),  # 10:00 – 15:00
    "s3": list(range(15, 21)),  # 15:00 – 20:00
    "s4": list(range(20, 24)),  # 20:00 – 23:00
}

_SLOT_LABELS: dict[str, str] = {
    "s1": "05:00 - 10:00",
    "s2": "10:00 - 15:00",
    "s3": "15:00 - 20:00",
    "s4": "20:00 - 23:00",
}

_REGIONS: dict[str, tuple[str, list[str]]] = {
    "north": (
        "北部",
        ["台北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "宜蘭縣"],
    ),
    "central": ("中部", ["台中市", "苗栗縣", "彰化縣", "南投縣", "雲林縣"]),
    "south": ("南部", ["高雄市", "台南市", "嘉義市", "嘉義縣", "屏東縣"]),
    "east": ("東部", ["花蓮縣", "台東縣"]),
    "island": ("離島", ["澎湖縣", "金門縣", "連江縣"]),
}

PERSISTENT_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔥 可報名賽事"), KeyboardButton("⏳ 即將開放")],
        [KeyboardButton("⚙️ 設定")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

WELCOME_TEXT = (
    "歡迎加入台灣路跑通知！🏃‍♂️🔥\n\n"
    "準備好開跑了嗎？每天在你設定的時間，幫你抓出最新開放報名的賽事，一場都不放過！\n\n"
    "用下方按鈕，隨時查活動或改設定 💪"
)

_ASK_SLOT_TEXT = "想在每天哪個時段收到賽事通知？選一個吧 ⏰"
_ASK_CITY_TEXT = "想追哪個地區的賽事？選你的主場 📍"
_ASK_SETTINGS_TEXT = "想調整什麼？⚙️"


def get_db() -> FirestoreClient:
    return FirestoreClient(project_id=os.environ["GCP_PROJECT_ID"])


def build_slot_keyboard() -> InlineKeyboardMarkup:
    items = list(_SLOT_LABELS.items())
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(items), 2):
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"slot:{key}")
                for key, label in items[i : i + 2]
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_hour_keyboard(slot: str) -> InlineKeyboardMarkup:
    hours = _SLOT_HOURS.get(slot, [])
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(hours), 3):
        rows.append(
            [
                InlineKeyboardButton(f"{h:02d}:00", callback_data=f"hour:{h}")
                for h in hours[i : i + 3]
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_slot_keyboard_t() -> InlineKeyboardMarkup:
    """修改時間專用：slot_t: 前綴，不引導至地區選擇。"""
    items = list(_SLOT_LABELS.items())
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(items), 2):
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"slot_t:{key}")
                for key, label in items[i : i + 2]
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_hour_keyboard_t(slot: str) -> InlineKeyboardMarkup:
    """修改時間專用：hour_t: 前綴，選完後只更新時間。"""
    hours = _SLOT_HOURS.get(slot, [])
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(hours), 3):
        rows.append(
            [
                InlineKeyboardButton(f"{h:02d}:00", callback_data=f"hour_t:{h}")
                for h in hours[i : i + 3]
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_region_keyboard(hour: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("北部", callback_data=f"region:{hour}:north"),
                InlineKeyboardButton("中部", callback_data=f"region:{hour}:central"),
                InlineKeyboardButton("南部", callback_data=f"region:{hour}:south"),
            ],
            [
                InlineKeyboardButton("東部", callback_data=f"region:{hour}:east"),
                InlineKeyboardButton("離島", callback_data=f"region:{hour}:island"),
            ],
            [InlineKeyboardButton("全部地區", callback_data=f"city:{hour}:all")],
        ]
    )


def build_region_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("北部", callback_data="region_only:north"),
                InlineKeyboardButton("中部", callback_data="region_only:central"),
                InlineKeyboardButton("南部", callback_data="region_only:south"),
            ],
            [
                InlineKeyboardButton("東部", callback_data="region_only:east"),
                InlineKeyboardButton("離島", callback_data="region_only:island"),
            ],
            [InlineKeyboardButton("全部地區", callback_data="city_only:all")],
        ]
    )


def build_city_keyboard_for_region(region_key: str, hour: int) -> InlineKeyboardMarkup:
    cities = _REGIONS[region_key][1]
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(cities), 3):
        rows.append(
            [
                InlineKeyboardButton(city, callback_data=f"city:{hour}:{city}")
                for city in cities[i : i + 3]
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_city_only_keyboard_for_region(region_key: str) -> InlineKeyboardMarkup:
    cities = _REGIONS[region_key][1]
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(cities), 3):
        rows.append(
            [
                InlineKeyboardButton(city, callback_data=f"city_only:{city}")
                for city in cities[i : i + 3]
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏰ 改時間", callback_data="settings_time"),
                InlineKeyboardButton("📍 改地區", callback_data="settings_city"),
            ],
            [InlineKeyboardButton("取消訂閱", callback_data="unsubscribe_btn")],
        ]
    )


def _city_display(city: str) -> str:
    return "全台灣" if city == "all" else city


def _settings_confirmation(hour: int, city: str) -> str:
    return f"搞定！每天 {hour:02d}:00 幫你追 {_city_display(city)} 的最新賽事 🔥"


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
        f"{label} 收到！再選個準確時間 ⏰",
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
        f"每天 {hour:02d}:00 準時叫你開跑 🏃\n\n{_ASK_CITY_TEXT}",
        reply_markup=build_region_keyboard(hour),
    )


async def city_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """使用者選擇城市後，儲存訂閱並顯示確認訊息。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_user is not None
    await query.answer()

    parts = query.data.split(":", 2)
    hour = int(parts[1])
    city = parts[2]

    db = get_db()
    is_new = db.subscribe(
        user_id=update.effective_user.id, notification_hour=hour, preferred_city=city
    )

    city_label = _city_display(city)
    if is_new:
        msg = (
            f"設定完成，準備開跑！🔥\n\n"
            f"從今天起，每天 {hour:02d}:00 把 {city_label} 最新可報名的賽事送到你面前，一場都不錯過 🏃‍♂️\n\n"
            f"衝吧，賽事連連 💪"
        )
    else:
        msg = _settings_confirmation(hour, city)
    await query.edit_message_text(msg)


async def open_settings_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """顯示設定選單（由推播頁腳按鈕觸發）。"""
    query = update.callback_query
    assert query is not None
    await query.answer()
    await query.edit_message_text(
        _ASK_SETTINGS_TEXT, reply_markup=build_settings_keyboard()
    )


async def settings_time_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """修改推播時間：顯示時段選擇鍵盤（slot_t: 前綴，完成後只更新時間）。"""
    query = update.callback_query
    assert query is not None
    await query.answer()
    await query.edit_message_text(_ASK_SLOT_TEXT, reply_markup=build_slot_keyboard_t())


async def slot_time_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """修改時間：選擇時段後顯示具體時間按鈕（hour_t: 前綴）。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    await query.answer()
    slot = query.data.split(":", 1)[1]
    label = _SLOT_LABELS.get(slot, slot)
    await query.edit_message_text(
        f"{label} 收到！再選個準確時間 ⏰",
        reply_markup=build_hour_keyboard_t(slot),
    )


async def hour_time_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """修改時間：只儲存新時段，讀回既有地區，顯示完整確認訊息。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_user is not None
    await query.answer()
    hour = int(query.data.split(":", 1)[1])
    db = get_db()
    db.update_hour(user_id=update.effective_user.id, notification_hour=hour)
    city = db.get_user_city(update.effective_user.id)
    await query.edit_message_text(_settings_confirmation(hour, city))


async def settings_city_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """修改推播地區：顯示城市選擇鍵盤（不影響推播時間）。"""
    query = update.callback_query
    assert query is not None
    await query.answer()
    await query.edit_message_text(
        _ASK_CITY_TEXT, reply_markup=build_region_only_keyboard()
    )


async def region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """初次設定：使用者選擇地區後，顯示該地區的縣市清單。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    await query.answer()
    parts = query.data.split(":", 2)
    hour = int(parts[1])
    region_key = parts[2]
    region_label, _ = _REGIONS[region_key]
    await query.edit_message_text(
        f"{region_label} 有這些縣市，挑你的主場 📍",
        reply_markup=build_city_keyboard_for_region(region_key, hour),
    )


async def region_only_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """設定修改：使用者選擇地區後，顯示該地區的縣市清單（不影響推播時段）。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    await query.answer()
    region_key = query.data.split(":", 1)[1]
    region_label, _ = _REGIONS[region_key]
    await query.edit_message_text(
        f"{region_label} 有這些縣市，挑你的主場 📍",
        reply_markup=build_city_only_keyboard_for_region(region_key),
    )


async def city_only_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """只更新城市偏好，不動推播時段。"""
    query = update.callback_query
    assert query is not None
    assert query.data is not None
    assert update.effective_user is not None
    await query.answer()

    city = query.data.split(":", 1)[1]
    db = get_db()
    db.update_city(user_id=update.effective_user.id, preferred_city=city)
    hour = db.get_notification_hour(update.effective_user.id)
    msg = (
        _settings_confirmation(hour, city)
        if hour is not None
        else f"更新好了！接下來幫你追 {_city_display(city)} 的賽事 🔥"
    )
    await query.edit_message_text(msg)


async def unsubscribe_btn_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """透過按鈕取消訂閱。"""
    query = update.callback_query
    assert query is not None
    assert update.effective_user is not None
    await query.answer()

    db = get_db()
    db.unsubscribe(user_id=update.effective_user.id)
    await query.edit_message_text("已取消訂閱，隨時想跑再回來找我 👋")


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    text = update.message.text
    if text == "🔥 可報名賽事":
        await _handle_open_events(update, context)
    elif text == "⏳ 即將開放":
        await _handle_upcoming_events(update, context)
    elif text == "⚙️ 設定":
        await update.message.reply_text(
            _ASK_SETTINGS_TEXT, reply_markup=build_settings_keyboard()
        )


def _get_cloud_run_url() -> str:
    return (
        os.environ.get("GCP_CLOUD_RUN_URL")
        or os.environ.get("WEBHOOK_URL", "").rsplit("/webhook", 1)[0]
    )


async def _handle_open_events(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    assert update.effective_user is not None
    cloud_run_url = _get_cloud_run_url()
    city = get_db().get_user_city(update.effective_user.id)
    await update.message.reply_text(
        "點下方按鈕，看看現在能報哪些賽事 🔥",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔥 開始瀏覽賽事",
                        web_app=WebAppInfo(
                            url=f"{cloud_run_url}/webapp?type=open&city={quote(city)}"
                        ),
                    )
                ]
            ]
        ),
    )


async def _handle_upcoming_events(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    assert update.effective_user is not None
    cloud_run_url = _get_cloud_run_url()
    city = get_db().get_user_city(update.effective_user.id)
    await update.message.reply_text(
        "點下方按鈕，搶先看 30 天內即將開放的賽事 ⏳",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⏳ 看即將開放",
                        web_app=WebAppInfo(
                            url=f"{cloud_run_url}/webapp?type=upcoming&city={quote(city)}"
                        ),
                    )
                ]
            ]
        ),
    )


async def unsubscribe_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    assert update.message is not None
    assert update.effective_user is not None
    db = get_db()
    db.unsubscribe(user_id=update.effective_user.id)
    await update.message.reply_text("已取消訂閱，隨時想跑再回來找我 👋")
