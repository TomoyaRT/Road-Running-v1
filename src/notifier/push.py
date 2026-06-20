from __future__ import annotations

import logging
from datetime import date

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.cards import send_carousel_start
from src.bot.handlers import get_db
from src.scraper.running_biji import (
    RaceEvent,
    filter_events_by_city,
    filter_open_events,
)

logger = logging.getLogger(__name__)

_FOOTER_TEXT = "如需修改通知時間或地區，請點選下方按鈕。"


async def notify_users(bot: Bot, hour: int) -> None:
    db = get_db()
    users = db.get_users_for_hour(hour=hour)

    if not users:
        logger.info(f"Hour {hour}: no subscribers, skip")
        return

    events = db.get_events()
    open_events = filter_open_events(events, date.today())

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
    try:
        await send_carousel_start(bot, uid, events, "o", city)
    except Exception:
        logger.exception(f"Failed to send carousel to user {uid}")
        return

    try:
        await bot.send_message(
            chat_id=uid,
            text=_FOOTER_TEXT,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("設定", callback_data="open_settings")]]
            ),
        )
    except Exception:
        logger.exception(f"Failed to send footer to user {uid}")

    logger.info(f"Notified user {uid}: {len(events)} events (city={city})")
