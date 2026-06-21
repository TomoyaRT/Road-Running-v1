from __future__ import annotations

import logging
from urllib.parse import quote

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.bot.handlers import _get_cloud_run_url, get_db
from src.scraper.running_biji import (
    RaceEvent,
    filter_events_by_city,
)
from src.utils import tw_today

logger = logging.getLogger(__name__)


async def notify_users(bot: Bot, hour: int) -> None:
    db = get_db()
    users = db.get_users_for_hour(hour=hour)

    if not users:
        logger.info(f"Hour {hour}: no subscribers, skip")
        return

    today = tw_today()
    open_events = db.get_open_events("all", today)

    if not open_events:
        logger.info(f"Hour {hour}: no open events, skip")
        return

    for user in users:
        uid = user["user_id"]
        city = user.get("preferred_city", "all")
        city_events = filter_events_by_city(open_events, city)
        if not city_events:
            logger.info(f"Hour {hour}: no events for user {uid} (city={city}), skip")
            continue
        await _notify_one_user(bot, uid, city_events, city)


async def _notify_one_user(
    bot: Bot, uid: int, events: list[RaceEvent], city: str
) -> None:
    label = "全台灣" if city == "all" else city
    text = (
        f"熱血開跑！🔥 {label}現在有 {len(events)} 場賽事開放報名，\n"
        "點下方按鈕，手刀搶名額別錯過 🏃‍♂️"
    )
    webapp_url = f"{_get_cloud_run_url()}/webapp?type=open&city={quote(city)}"
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔥 手刀搶賽事", web_app=WebAppInfo(url=webapp_url))]]
    )
    try:
        await bot.send_message(chat_id=uid, text=text, reply_markup=markup)
    except Exception:
        logger.exception(f"Failed to notify user {uid}")
        return

    logger.info(f"Notified user {uid}: {len(events)} events (city={city})")
