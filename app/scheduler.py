from typing import Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from aiogram import Bot

from .db import Database
from .gemini import GeminiClient


def setup_scheduler(bot: Bot, db: Database, gemini: GeminiClient, cron: str, tz: str) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(tz))

    async def job_send_daily():
        # Получаем совет у Gemini (один раз на рассылку)
        tip = gemini.daily_tip()
        # Отправляем всем пользователям
        users = db.list_users()
        for u in users:
            try:
                await bot.send_message(chat_id=u.chat_id, text=f"Совет дня:\n{tip}")
            except Exception:
                # Игнорируем ошибки отправки конкретному пользователю
                pass

    # Cron format: "min hour dom month dow" — как в .env.example
    minute, hour, day, month, dow = cron.split()
    trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow, timezone=pytz.timezone(tz))
    scheduler.add_job(job_send_daily, trigger=trigger, id="daily_tip", replace_existing=True)
    return scheduler

