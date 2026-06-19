from __future__ import annotations

import logging
import os

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler

from src.bot.handlers import start_command, upcoming_events_callback

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(
        CallbackQueryHandler(upcoming_events_callback, pattern="^upcoming_events$")
    )

    logger.info("Bot starting (long-polling mode)")
    app.run_polling()


if __name__ == "__main__":
    main()
