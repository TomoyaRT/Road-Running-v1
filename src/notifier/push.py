from __future__ import annotations

import logging
from datetime import date

from telegram import Bot

from src.bot.handlers import get_db
from src.scraper.running_biji import RaceEvent, fetch_events, filter_open_events

logger = logging.getLogger(__name__)

_NO_EVENTS_TEXT = "今日沒有可報名的路跑活動，明天再來看看！"


def build_notification_text(events: list[RaceEvent]) -> str:
    """根據可報名活動清單，建立推播訊息文字。"""
    if not events:
        return _NO_EVENTS_TEXT

    lines = [f"🏃 今日可報名的路跑活動（共 {len(events)} 筆）：\n"]
    for e in events:
        end = e.reg_end.strftime("%m/%d") if e.reg_end else "?"
        lines.append(f"• {e.name}（{e.location}）\n  截止：{end}  {e.url}")
    return "\n".join(lines)


async def notify_users(bot: Bot, hour: int) -> None:
    """查詢指定小時的訂閱使用者，推播今日可報名活動。"""
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

    text = build_notification_text(open_events)
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text)
            logger.info(f"Notified user {uid}")
        except Exception:
            logger.exception(f"Failed to notify user {uid}")
