from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta

import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .db import Database
from .gemini import GeminiClient
from .keyboards import main_menu_keyboard
from .services.assignments import ensure_daily_assignment


class LessonScheduler:
    def __init__(
        self,
        bot: Bot,
        db: Database,
        gemini: GeminiClient,
        *,
        default_cron: str,
        timezone: str,
    ) -> None:
        self.bot = bot
        self.db = db
        self.gemini = gemini
        self.default_cron = default_cron
        self.timezone = pytz.timezone(timezone)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.logger = logging.getLogger("learn_en_bot.scheduler")

    async def initialize(self) -> None:
        await self._schedule_existing_custom_jobs()
        self._schedule_default_job()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def reschedule_user(self, user_id: int) -> None:
        with suppress(Exception):
            self.scheduler.remove_job(self._daily_job_id(user_id))

        user = await asyncio.to_thread(self.db.get_user_by_id, user_id)
        if not user or user.daily_hour is None or user.daily_minute is None:
            return

        self._schedule_daily_job(user.id, user.daily_hour, user.daily_minute)

    def plan_followups(self, user_id: int, assignment_id: int) -> None:
        now = datetime.now(self.timezone)
        follow1_time = now + timedelta(hours=4)
        follow2_time = now + timedelta(hours=9)

        self.scheduler.add_job(
            self._send_followup,
            trigger=DateTrigger(run_date=follow1_time, timezone=self.timezone),
            args=[user_id, assignment_id, 1],
            id=self._followup_job_id(assignment_id, 1),
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._send_followup,
            trigger=DateTrigger(run_date=follow2_time, timezone=self.timezone),
            args=[user_id, assignment_id, 2],
            id=self._followup_job_id(assignment_id, 2),
            replace_existing=True,
        )

    async def _schedule_existing_custom_jobs(self) -> None:
        users = await asyncio.to_thread(self.db.list_users)
        for user in users:
            if user.daily_hour is None or user.daily_minute is None:
                continue
            self._schedule_daily_job(user.id, user.daily_hour, user.daily_minute)

    def _schedule_default_job(self) -> None:
        try:
            minute, hour, day, month, dow = self.default_cron.split()
        except ValueError:
            self.logger.error("Invalid cron format for default schedule: %s", self.default_cron)
            return

        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=dow,
            timezone=self.timezone,
        )
        self.scheduler.add_job(
            self._run_default_job,
            trigger=trigger,
            id="daily_assignment",
            replace_existing=True,
        )

    async def _run_default_job(self) -> None:
        users = await asyncio.to_thread(self.db.list_users_without_daily_time)
        for user in users:
            try:
                await self._send_assignment_to_user(user, schedule_followups=True)
            except Exception:
                self.logger.exception("Failed to send scheduled assignment to chat %s", user.chat_id)

    def _schedule_daily_job(self, user_id: int, hour: int, minute: int) -> None:
        trigger = CronTrigger(hour=hour, minute=minute, timezone=self.timezone)
        self.scheduler.add_job(
            self._send_custom_job,
            trigger=trigger,
            args=[user_id],
            id=self._daily_job_id(user_id),
            replace_existing=True,
        )

    async def _send_custom_job(self, user_id: int) -> None:
        user = await asyncio.to_thread(self.db.get_user_by_id, user_id)
        if not user:
            return
        await self._send_assignment_to_user(user, schedule_followups=True)

    async def _send_assignment_to_user(self, user, *, schedule_followups: bool) -> None:
        assignment, text, created = await ensure_daily_assignment(
            self.db, self.gemini, user, force_new=False
        )
        try:
            await self.bot.send_message(
                chat_id=user.chat_id,
                text=text,
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            self.logger.exception("Failed to send assignment message to chat %s", user.chat_id)
            return

        if schedule_followups and created:
            self.plan_followups(user.id, assignment.id)

    async def _send_followup(self, user_id: int, assignment_id: int, which: int) -> None:
        user = await asyncio.to_thread(self.db.get_user_by_id, user_id)
        if not user:
            return

        assignment = await asyncio.to_thread(self.db.get_today_assignment, user.id)
        if not assignment or assignment.id != assignment_id or assignment.status == "mastered":
            return

        if which == 1 and assignment.followup1_sent:
            return
        if which == 2 and assignment.followup2_sent:
            return

        reminder = (
            f"<b>Напоминание:</b> вернись к фразовому глаголу \"{assignment.phrasal_verb}\"."
            " Составь ещё одно короткое предложение — я подскажу, всё ли верно."
        )

        try:
            await self.bot.send_message(chat_id=user.chat_id, text=reminder)
            await asyncio.to_thread(self.db.mark_followup_sent, assignment.id, which)
        except Exception:
            self.logger.exception("Failed to send follow-up to chat %s", user.chat_id)

    @staticmethod
    def _daily_job_id(user_id: int) -> str:
        return f"daily_assignment_{user_id}"

    @staticmethod
    def _followup_job_id(assignment_id: int, which: int) -> str:
        return f"followup{which}_{assignment_id}"


async def setup_scheduler(
    bot: Bot,
    db: Database,
    gemini: GeminiClient,
    cron: str,
    tz: str,
) -> LessonScheduler:
    scheduler = LessonScheduler(bot, db, gemini, default_cron=cron, timezone=tz)
    await scheduler.initialize()
    return scheduler

