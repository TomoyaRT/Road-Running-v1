from __future__ import annotations

import datetime
import json
import logging
import os

from quart import Quart, Response, request, send_from_directory
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
    city_only_callback,
    get_db,
    handle_text_message,
    hour_callback,
    hour_time_callback,
    open_settings_callback,
    region_callback,
    region_only_callback,
    settings_city_callback,
    settings_time_callback,
    slot_callback,
    slot_time_callback,
    start_command,
    unsubscribe_btn_callback,
    unsubscribe_command,
)
from src.bot.webapp_api import validate_init_data
from src.notifier.push import notify_users
from src.scraper.crawler import crawl_and_store
from src.utils import tw_today

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

quart_app = Quart(__name__)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_telegram_app: Application | None = None  # type: ignore[type-arg]


def _build_app() -> Application:  # type: ignore[type-arg]
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CallbackQueryHandler(slot_callback, pattern=r"^slot:"))
    app.add_handler(CallbackQueryHandler(slot_time_callback, pattern=r"^slot_t:"))
    app.add_handler(CallbackQueryHandler(hour_callback, pattern=r"^hour:"))
    app.add_handler(CallbackQueryHandler(hour_time_callback, pattern=r"^hour_t:"))
    app.add_handler(CallbackQueryHandler(region_callback, pattern=r"^region:"))
    app.add_handler(
        CallbackQueryHandler(region_only_callback, pattern=r"^region_only:")
    )
    app.add_handler(CallbackQueryHandler(city_callback, pattern=r"^city:"))
    app.add_handler(CallbackQueryHandler(city_only_callback, pattern=r"^city_only:"))
    app.add_handler(
        CallbackQueryHandler(open_settings_callback, pattern=r"^open_settings$")
    )
    app.add_handler(
        CallbackQueryHandler(settings_time_callback, pattern=r"^settings_time$")
    )
    app.add_handler(
        CallbackQueryHandler(settings_city_callback, pattern=r"^settings_city$")
    )
    app.add_handler(
        CallbackQueryHandler(unsubscribe_btn_callback, pattern=r"^unsubscribe_btn$")
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
    try:
        await notify_users(bot=bot, hour=tw_hour)
        return Response("ok", status=200)
    except Exception:
        logger.exception("notify failed")
        return Response("notify failed", status=500)


@quart_app.route("/crawl", methods=["POST"])
async def crawl_endpoint() -> Response:
    """Cloud Scheduler 定期觸發：爬取、過濾路跑、補齊圖片與報名連結後存進 DB。"""
    try:
        count = await crawl_and_store(get_db())
        return Response(f"stored {count} events", status=200)
    except Exception:
        logger.exception("crawl failed")
        return Response("crawl failed", status=500)


@quart_app.route("/webapp")
async def webapp_page() -> Response:
    return await send_from_directory(_STATIC_DIR, "index.html")


@quart_app.route("/static/<path:filename>")
async def static_file(filename: str) -> Response:
    return await send_from_directory(_STATIC_DIR, filename)


@quart_app.route("/api/events")
async def api_events() -> Response:
    init_data = request.headers.get("Authorization", "")
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    if not validate_init_data(init_data, bot_token):
        return Response("Unauthorized", status=401)

    event_type = request.args.get("type", "open")
    city = request.args.get("city", "all")

    db = get_db()
    today = tw_today()
    events = (
        db.get_upcoming_events(city, today)
        if event_type == "upcoming"
        else db.get_open_events(city, today)
    )

    result = [
        {
            "name": e.name,
            "race_date": e.race_date.isoformat(),
            "location": e.location,
            "url": e.official_url or e.url,
            "reg_start": e.reg_start.isoformat() if e.reg_start else None,
            "reg_end": e.reg_end.isoformat() if e.reg_end else None,
            "city": e.city,
            "image_url": e.image_url,
            "organizer": e.organizer,
            "categories": e.categories,
        }
        for e in events
    ]
    return Response(
        json.dumps({"events": result}, ensure_ascii=False),
        status=200,
        content_type="application/json; charset=utf-8",
    )


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
