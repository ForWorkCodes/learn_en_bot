import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import load_settings
from .db import Database
from .gemini import GeminiClient
from .handlers import start_router, chat_router, lesson_router
from .handlers import start as start_module
from .handlers import chat as chat_module
from .handlers import lesson as lesson_module
from .scheduler import setup_scheduler


def setup_logging() -> None:
    fmt = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)

    project_root = Path(__file__).resolve().parents[1]
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(logs_dir / "bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    # Avoid double-adding the handler if reloads happen
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(file_handler)


logger = logging.getLogger("learn_en_bot")


async def main() -> None:
    setup_logging()
    settings = load_settings()

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in environment")

    # DB
    db = Database(settings.database_url)
    db.init_db()

    # Gemini
    gemini = GeminiClient(settings.gemini_api_key)

    # Bot
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    scheduler = await setup_scheduler(
        bot,
        db,
        gemini,
        cron=settings.schedule_cron,
        tz=settings.tz,
    )
    scheduler.start()

    # Handlers
    start_module.setup(start_router, db, scheduler)
    chat_module.setup(chat_router, db, gemini)
    lesson_module.setup(lesson_router, db, gemini, scheduler)
    dp.include_router(start_router)
    dp.include_router(chat_router)
    dp.include_router(lesson_router)

    # Bot menu commands
    try:
        from aiogram.types import BotCommand
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать"),
            BotCommand(command="lesson", description="Получить фразовый глагол"),
        ])
    except Exception:
        logger.warning("Failed to set bot commands", exc_info=True)

    # Ensure commands descriptions are set in readable Russian
    try:
        from aiogram.types import BotCommand
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать"),
            BotCommand(command="lesson", description="Получить фразовый глагол"),
        ])
    except Exception:
        logger.warning("Failed to override bot commands", exc_info=True)

    logger.info("Bot started. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
