"""本地測試推播腳本：直接對指定 user_id 送出目前可報名的路跑活動卡片。"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path

# 載入 .env
env_path = Path(__file__).parent.parent / ".env"
for line in env_path.read_text().splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val:
            os.environ.setdefault(key, val)

from telegram import Bot

from src.bot.cards import send_event_card
from src.scraper.running_biji import fetch_events, filter_open_events

TARGET_USER_ID = 8572749755


async def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    async with Bot(token) as bot:
        print(f"Bot: {(await bot.get_me()).username}")
        events = fetch_events()
        open_events = filter_open_events(events, date.today())
        print(f"Found {len(open_events)} open events")

        if not open_events:
            await bot.send_message(
                chat_id=TARGET_USER_ID,
                text="今日沒有可報名的路跑活動，明天再來看看！",
            )
            print("Sent 'no events' message")
            return

        for event in open_events:
            await send_event_card(bot, TARGET_USER_ID, event)
            print(f"  Sent card: {event.name}")

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        await bot.send_message(
            chat_id=TARGET_USER_ID,
            text="如需修改通知時間，請點選下方按鈕。",
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
        print("Done — check Telegram!")


if __name__ == "__main__":
    asyncio.run(main())
