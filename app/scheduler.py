from typing import Callable
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import pytz

from aiogram import Bot

from .db import Database
from .gemini import GeminiClient


def setup_scheduler(bot: Bot, db: Database, gemini: GeminiClient, cron: str, tz: str) -> AsyncIOScheduler:
    timezone = pytz.timezone(tz)
    scheduler = AsyncIOScheduler(timezone=timezone)

    async def send_initial_assignment(user) -> None:
        data = await asyncio.to_thread(
            gemini.generate_phrasal_verb, user_hint=user.username or str(user.chat_id)
        )
        import json
        assgn = db.ensure_today_assignment(
            user,
            verb=data["verb"],
            translation=data["translation"],
            explanation=data["explanation"],
            examples_json=json.dumps(data.get("examples", []), ensure_ascii=False),
        )
        text = (
            f"Твой фразовый глагол дня: {assgn.phrasal_verb} — {assgn.translation}\n"
            f"Пояснение: {assgn.explanation}\n\n"
            f"Примеры:\n"
        )
        import json
        try:
            examples = json.loads(assgn.examples_json)
        except Exception:
            examples = []
        for ex in examples:
            text += f"• {ex}\n"
        text += "\nНапиши предложение с этим глаголом. Я помогу исправить и объяснить."
        await bot.send_message(chat_id=user.chat_id, text=text)

        # Запланировать два последующих напоминания на сегодня
        now = datetime.now(timezone)
        follow1_time = now + timedelta(hours=4)
        follow2_time = now + timedelta(hours=9)

        async def followup_job(user_id: int, which: int):
            users = {u.id: u for u in db.list_users()}
            u = users.get(user_id)
            if not u:
                return
            assgn = db.get_today_assignment(u.id)
            if not assgn or assgn.status == "mastered":
                return
            if which == 1 and assgn.followup1_sent:
                return
            if which == 2 and assgn.followup2_sent:
                return
            prompt = (
                f"Напоминание по глаголу: {assgn.phrasal_verb}. "
                "Составь ещё одно короткое предложение, и я подскажу, всё ли ок."
            )
            try:
                await bot.send_message(chat_id=u.chat_id, text=prompt)
                db.mark_followup_sent(assgn.id, which)
            except Exception:
                pass

        scheduler.add_job(
            followup_job,
            trigger=DateTrigger(run_date=follow1_time, timezone=timezone),
            args=[user.id, 1],
            id=f"followup1_{user.id}_{assgn.date_assigned.isoformat()}",
            replace_existing=True,
        )
        scheduler.add_job(
            followup_job,
            trigger=DateTrigger(run_date=follow2_time, timezone=timezone),
            args=[user.id, 2],
            id=f"followup2_{user.id}_{assgn.date_assigned.isoformat()}",
            replace_existing=True,
        )

    async def job_send_daily():
        users = db.list_users()
        for u in users:
            try:
                await send_initial_assignment(u)
            except Exception:
                pass

    # Cron format: "min hour dom month dow" — как в .env.example
    minute, hour, day, month, dow = cron.split()
    trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow, timezone=timezone)
    scheduler.add_job(job_send_daily, trigger=trigger, id="daily_assignment", replace_existing=True)
    return scheduler
