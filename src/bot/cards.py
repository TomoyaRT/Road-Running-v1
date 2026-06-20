from __future__ import annotations

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from src.scraper.running_biji import RaceEvent

logger = logging.getLogger(__name__)


def format_card_text(event: RaceEvent) -> str:
    """建立活動卡片的 HTML 格式文字（單張卡片用）。"""
    reg_start = event.reg_start.strftime("%m/%d") if event.reg_start else "?"
    reg_end = event.reg_end.strftime("%m/%d") if event.reg_end else "?"
    lines = [
        f"<b>{event.name}</b>",
        event.race_date.strftime("%Y-%m-%d"),
        "",
        f"報名時間：{reg_start} - {reg_end}",
        f"活動地點：{event.location}",
    ]
    if event.organizer:
        lines.append(f"主辦單位：{event.organizer}")
    if event.categories:
        lines.append(f"報名組別：{' / '.join(event.categories)}")
    return "\n".join(lines)


def _reg_markup(event: RaceEvent) -> InlineKeyboardMarkup:
    reg_url = event.official_url or event.url
    return InlineKeyboardMarkup([[InlineKeyboardButton("立刻報名", url=reg_url)]])


async def send_event_card(bot: Bot, chat_id: int, event: RaceEvent) -> None:
    """發送活動卡片（有圖用 send_photo，無圖用 send_message）。"""
    text = format_card_text(event)
    markup = _reg_markup(event)
    if event.image_url:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=event.image_url,
                caption=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            return
        except Exception:
            logger.warning(f"send_photo failed for {event.name}, fallback to text")
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=markup,
    )
