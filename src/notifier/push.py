from __future__ import annotations

import logging
from datetime import date

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.cards import send_event_card
from src.bot.handlers import get_db
from src.scraper.running_biji import RaceEvent, fetch_events, filter_open_events

logger = logging.getLogger(__name__)

_NO_EVENTS_TEXT = "今日沒有可報名的路跑活動，明天再來看看！"
_FOOTER_TEXT = "如需修改通知時間，請點選下方按鈕。"


async def notify_users(bot: Bot, hour: int) -> None:
    db = get_db()
    user_ids = db.get_users_for_hour(hour=hour)

    if not user_ids:
        logger.info(f"Hour {hour}: no subscribers, skip")
        return

    events = fetch_events()
    open_events = filter_open_events(events, date.today())

    if not open_events:
        logger.info(f"Hour {hour}: no open events, skip")
        return

    for uid in user_ids:
        await _notify_one_user(bot, uid, open_events)


async def _notify_one_user(bot: Bot, uid: int, open_events: list[RaceEvent]) -> None:
    sent = 0
    for event in open_events:
        try:
            await send_event_card(bot, uid, event)
            sent += 1
        except Exception:
            logger.exception(f"Failed to send card for {event.name} to user {uid}")

    try:
        await bot.send_message(
            chat_id=uid,
            text=_FOOTER_TEXT,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "修改推播時間", callback_data="modify_schedule"
                        )
                    ]
                ]
            ),
        )
    except Exception:
        logger.exception(f"Failed to send footer to user {uid}")

    logger.info(f"Notified user {uid}: {sent}/{len(open_events)} cards sent")
