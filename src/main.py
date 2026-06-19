from __future__ import annotations

import datetime
import logging
import os

from quart import Quart, Response, request
from telegram import Bot, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.bot.handlers import (
    city_callback,
    handle_text_message,
    hour_callback,
    modify_schedule_callback,
    nav_callback,
    slot_callback,
    start_command,
    unsubscribe_command,
)
from src.notifier.push import notify_users

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

quart_app = Quart(__name__)

_telegram_app: Application | None = None  # type: ignore[type-arg]


def _build_app() -> Application:  # type: ignore[type-arg]
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^slot:"))
    app.add_handler(CallbackQueryHandler(hour_callback, pattern=r"^hour:"))
    app.add_handler(CallbackQueryHandler(city_callback, pattern=r"^city:"))
    app.add_handler(CallbackQueryHandler(nav_callback, pattern=r"^nav:"))
    app.add_handler(
        CallbackQueryHandler(modify_schedule_callback, pattern=r"^modify_schedule$")
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    return app


@quart_app.before_serving
async def startup() -> None:
    global _telegram_app
    _telegram_app = _build_app()
    await _telegram_app.initialize()
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        secret = os.environ.get("WEBHOOK_SECRET", "")
        await _telegram_app.bot.set_webhook(url=webhook_url, secret_token=secret)
        logger.info(f"Webhook set to {webhook_url}")
    else:
        logger.warning("WEBHOOK_URL not set, skipping webhook registration")


@quart_app.route("/webhook", methods=["POST"])
async def webhook() -> Response:
    assert _telegram_app is not None
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
    assert _telegram_app is not None
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
