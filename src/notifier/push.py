from __future__ import annotations

import logging
from datetime import date

from telegram import Bot

from src.bot.handlers import get_db
from src.scraper.running_biji import RaceEvent, fetch_events, filter_open_events

logger = logging.getLogger(__name__)

_NO_EVENTS_TEXT = "今日沒有可報名的路跑活動，明天再來看看！"
_MAX_LEN = 4096


def build_notification_text(events: list[RaceEvent]) -> str:
    if not events:
        return _NO_EVENTS_TEXT
    header = f"今日可報名的路跑活動（共 {len(events)} 筆）："
    blocks: list[str] = []
    for e in events:
        end = e.reg_end.strftime("%m/%d") if e.reg_end else "?"
        blocks.append(f"• {e.name}（{e.location}）\n  截止：{end}  {e.url}")
    return header + "\n\n" + "\n\n".join(blocks)


def _chunk_text(text: str) -> list[str]:
    if len(text) <= _MAX_LEN:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        if len(block) > _MAX_LEN:
            for line in block.split("\n"):
                safe_line = line[:_MAX_LEN]
                candidate = f"{current}\n{safe_line}" if current else safe_line
                if len(candidate) <= _MAX_LEN:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    current = safe_line
        else:
            candidate = f"{current}\n\n{block}" if current else block
            if len(candidate) <= _MAX_LEN:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = block
    if current:
        chunks.append(current)
    return chunks


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

    chunks = _chunk_text(build_notification_text(open_events))
    for uid in user_ids:
        sent = 0
        for i, chunk in enumerate(chunks):
            try:
                await bot.send_message(chat_id=uid, text=chunk)
                sent += 1
            except Exception:
                logger.exception(f"Failed to notify user {uid} chunk {i}")
        logger.info(f"Notified user {uid}: {sent}/{len(chunks)} chunks sent")
