from __future__ import annotations

import datetime
import logging
import os

from quart import Quart, Response, request
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler

from src.bot.handlers import (
    start_command,
    subscribe_command,
    unsubscribe_command,
    upcoming_events_callback,
)
from src.notifier.push import notify_users

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

quart_app = Quart(__name__)

_telegram_app = None


def _build_app() -> object:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(
        CallbackQueryHandler(upcoming_events_callback, pattern="^upcoming_events$")
    )
    return app


@quart_app.before_serving
async def startup() -> None:
    global _telegram_app
    _telegram_app = _build_app()
    await _telegram_app.initialize()
    webhook_url = os.environ["WEBHOOK_URL"]
    secret = os.environ.get("WEBHOOK_SECRET", "")
    await _telegram_app.bot.set_webhook(url=webhook_url, secret_token=secret)
    logger.info(f"Webhook set to {webhook_url}")


@quart_app.route("/webhook", methods=["POST"])
async def webhook() -> Response:
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        return Response("Unauthorized", status=401)

    data = await request.get_json()
    update = Update.de_json(data, _telegram_app.bot)
    await _telegram_app.process_update(update)
    return Response("ok", status=200)


@quart_app.route("/notify", methods=["POST"])
async def notify_endpoint() -> Response:
    """Cloud Scheduler 每小時觸發，推播當前台灣時段的訂閱者。"""
    tw_hour = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).hour
    bot: Bot = _telegram_app.bot
    await notify_users(bot=bot, hour=tw_hour)
    return Response("ok", status=200)


@quart_app.route("/health")
async def health() -> Response:
    return Response("ok", status=200)


def main() -> None:
    """本地開發用：long-polling 模式。"""
    app = _build_app()
    logger.info("Bot starting (long-polling mode)")
    app.run_polling()


if __name__ == "__main__":
    main()
