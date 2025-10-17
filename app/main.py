import asyncio
import logging

from aiogram import Bot, Dispatcher

from .config import load_settings
from .db import Database
from .gemini import GeminiClient
from .handlers import start_router, chat_router
from .handlers import start as start_module
from .handlers import chat as chat_module
from .scheduler import setup_scheduler


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("learn_en_bot")


async def main() -> None:
    settings = load_settings()

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in environment")

    # DB
    db = Database(settings.database_url)
    db.init_db()

    # Gemini
    gemini = GeminiClient(settings.gemini_api_key)

    # Bot
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    # Handlers
    start_module.setup(start_router, db)
    chat_module.setup(chat_router, db, gemini)
    dp.include_router(start_router)
    dp.include_router(chat_router)

    # Scheduler
    scheduler = setup_scheduler(bot, db, gemini, cron=settings.schedule_cron, tz=settings.tz)
    scheduler.start()

    logger.info("Bot started. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
