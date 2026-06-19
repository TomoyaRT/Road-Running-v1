from __future__ import annotations

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from src.scraper.running_biji import RaceEvent, fetch_official_url_async

logger = logging.getLogger(__name__)

PLACEHOLDER_IMAGE_URL = "https://placehold.co/600x300/eeeeee/999999.png"


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
    if event.categories:
        lines.append(f"報名組別：{' / '.join(event.categories)}")
    return "\n".join(lines)


def format_carousel_text(event: RaceEvent, index: int, total: int) -> str:
    """建立輪播卡片的 HTML 格式文字（含進度指示）。"""
    reg_start = event.reg_start.strftime("%m/%d") if event.reg_start else "?"
    reg_end = event.reg_end.strftime("%m/%d") if event.reg_end else "?"
    lines = [f"<b>{event.name}</b>"]
    if event.city:
        lines.append(event.city)
    lines += [
        f"活動日期：{event.race_date.strftime('%Y-%m-%d')}",
        f"活動地點：{event.location}",
        "",
        f"報名時間：{reg_start} - {reg_end}",
    ]
    if event.categories:
        lines.append(f"報名組別：{' / '.join(event.categories)}")
    lines.append(f"\n{index + 1} / {total}")
    return "\n".join(lines)


def build_nav_markup(
    event_type: str, index: int, total: int, city: str, reg_url: str
) -> InlineKeyboardMarkup:
    """建立輪播導航按鈕（← 上一個 / 下一個 → / 立刻報名）。"""
    nav_row: list[InlineKeyboardButton] = []
    if index > 0:
        nav_row.append(
            InlineKeyboardButton(
                "← 上一個", callback_data=f"nav:{event_type}:{index - 1}:{city}"
            )
        )
    if index < total - 1:
        nav_row.append(
            InlineKeyboardButton(
                "下一個 →", callback_data=f"nav:{event_type}:{index + 1}:{city}"
            )
        )

    rows: list[list[InlineKeyboardButton]] = []
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton("立刻報名", url=reg_url)])
    return InlineKeyboardMarkup(rows)


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


async def send_carousel_start(
    bot: Bot, chat_id: int, events: list[RaceEvent], event_type: str, city: str
) -> None:
    """發送輪播第一張卡片（含導航按鈕）。後續導航透過 nav_callback 處理。"""
    if not events:
        return
    event = events[0]
    total = len(events)
    official_url = await fetch_official_url_async(event.url) or event.url
    text = format_carousel_text(event, 0, total)
    markup = build_nav_markup(event_type, 0, total, city, official_url)
    photo = event.image_url or PLACEHOLDER_IMAGE_URL
    try:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=text,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception:
        logger.warning(f"send_photo failed for carousel {event.name}, fallback to text")
        await bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup
        )
