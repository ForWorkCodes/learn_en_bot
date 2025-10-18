from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta

import pytz
from aiogram import Bot
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .db import Database
from .gemini import GeminiClient
from .keyboards import main_menu_keyboard
from .markdown import bold, escape
from .messages import FormattedMessage, format_assignment_message
from .services.assignments import ensure_daily_assignment
from .tts import TextToSpeechService


class LessonScheduler:
    def __init__(
        self,
        bot: Bot,
        db: Database,
        gemini: GeminiClient,
        tts: TextToSpeechService,
        *,
        default_cron: str,
        timezone: str,
    ) -> None:
        self.bot = bot
        self.db = db
        self.gemini = gemini
        self.tts = tts
        self.default_cron = default_cron
        self.timezone = pytz.timezone(timezone)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.logger = logging.getLogger("learn_en_bot.scheduler")

    async def initialize(self) -> None:
        await self._schedule_existing_custom_jobs()
        self._schedule_default_job()
        await self._deliver_pending_assignments()

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
        base_dt = datetime.now(self.timezone)

        # Allowed window: Today 11:00–23:00 (inclusive), local tz
        window_start = base_dt.replace(hour=11, minute=0, second=0, microsecond=0)
        window_end = base_dt.replace(hour=23, minute=0, second=0, microsecond=0)

        # Proposals relative to assignment send time
        proposed_1 = base_dt + timedelta(hours=2)
        proposed_2 = base_dt + timedelta(hours=7)

        # Clamp to window and ensure strictly after base_dt
        follow_times = []
        for candidate in (proposed_1, proposed_2):
            # If before the window start, push to window start
            if candidate < window_start:
                candidate = window_start
            # If after window end, skip
            if candidate > window_end:
                continue
            # Ensure after assignment time
            if candidate <= base_dt:
                # If there is still time to send before window_end, try a small delta
                candidate = min(window_end, base_dt + timedelta(minutes=15))
                if candidate <= base_dt:
                    continue
            follow_times.append(candidate)

        # Deduplicate and keep chronological
        uniq = []
        for t in sorted(follow_times):
            if not uniq or (t - uniq[-1]).total_seconds() >= 60:
                uniq.append(t)

        # Schedule up to two follow-ups
        for idx, when in enumerate(uniq[:2], start=1):
            self.scheduler.add_job(
                self._send_followup,
                trigger=DateTrigger(run_date=when, timezone=self.timezone),
                args=[user_id, assignment_id, idx],
                id=self._followup_job_id(assignment_id, idx),
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
        need_followups = schedule_followups and (created or assignment.delivered_at is None)
        try:
            await self.bot.send_message(
                chat_id=user.chat_id,
                text=text.markdown,
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            self.logger.exception("Failed to send assignment message to chat %s", user.chat_id)
            self._schedule_delivery_retry(user.id, assignment.id)
            return

        await self._send_voice_message(user.chat_id, text)

        await asyncio.to_thread(self.db.mark_assignment_delivered, assignment.id)
        with suppress(Exception):
            self.scheduler.remove_job(self._delivery_retry_job_id(assignment.id))
        if need_followups and assignment.status == "assigned":
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
            f"{bold('Напоминание')}: {escape('вернись к фразовому глаголу')} «{escape(assignment.phrasal_verb)}». "
            f"{escape('Составь ещё одно короткое предложение — я подскажу, всё ли верно.')}"
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

    @staticmethod
    def _delivery_retry_job_id(assignment_id: int) -> str:
        return f"delivery_retry_{assignment_id}"

    async def _deliver_pending_assignments(self) -> None:
        assignments = await asyncio.to_thread(self.db.list_undelivered_assignments)
        today = datetime.now(self.timezone).date()
        for assignment in assignments:
            if assignment.date_assigned < today or assignment.status != "assigned":
                await asyncio.to_thread(self.db.mark_assignment_delivered, assignment.id)
                continue

            user = await asyncio.to_thread(self.db.get_user_by_id, assignment.user_id)
            if not user:
                await asyncio.to_thread(self.db.mark_assignment_delivered, assignment.id)
                continue

            await self._deliver_existing_assignment(user, assignment, schedule_followups=True)

    async def _retry_assignment_delivery(self, user_id: int, assignment_id: int) -> None:
        user = await asyncio.to_thread(self.db.get_user_by_id, user_id)
        if not user:
            await asyncio.to_thread(self.db.mark_assignment_delivered, assignment_id)
            return

        assignment = await asyncio.to_thread(self.db.get_assignment_by_id, assignment_id)
        if not assignment or assignment.delivered_at is not None:
            return

        today = datetime.now(self.timezone).date()
        if assignment.date_assigned < today or assignment.status != "assigned":
            await asyncio.to_thread(self.db.mark_assignment_delivered, assignment.id)
            return

        await self._deliver_existing_assignment(user, assignment, schedule_followups=True)

    def _schedule_delivery_retry(self, user_id: int, assignment_id: int, delay_seconds: int = 60) -> None:
        run_date = datetime.now(self.timezone) + timedelta(seconds=delay_seconds)
        self.scheduler.add_job(
            self._retry_assignment_delivery,
            trigger=DateTrigger(run_date=run_date, timezone=self.timezone),
            args=[user_id, assignment_id],
            id=self._delivery_retry_job_id(assignment_id),
            replace_existing=True,
        )

    async def _deliver_existing_assignment(self, user, assignment, *, schedule_followups: bool) -> None:
        text = format_assignment_message(
            verb=assignment.phrasal_verb,
            translation=assignment.translation,
            explanation=assignment.explanation,
            examples_json=assignment.examples_json,
        )
        try:
            await self.bot.send_message(
                chat_id=user.chat_id,
                text=text.markdown,
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            self.logger.exception("Failed to send assignment message to chat %s", user.chat_id)
            self._schedule_delivery_retry(user.id, assignment.id)
            return

        await self._send_voice_message(user.chat_id, text)

        await asyncio.to_thread(self.db.mark_assignment_delivered, assignment.id)
        with suppress(Exception):
            self.scheduler.remove_job(self._delivery_retry_job_id(assignment.id))

        if schedule_followups and assignment.status == "assigned":
            self.plan_followups(user.id, assignment.id)


    async def _send_voice_message(self, chat_id: int, formatted: FormattedMessage) -> None:
        plain_value = (formatted.plain or "").strip()
        if not plain_value:
            return

        try:
            audio_bytes = await asyncio.to_thread(self.tts.synthesize, plain_value)
        except Exception:
            self.logger.exception("Failed to generate voice message for chat %s", chat_id)
            return

        if not audio_bytes:
            return

        audio = BufferedInputFile(audio_bytes, filename="assignment.mp3")
        try:
            await self.bot.send_audio(chat_id=chat_id, audio=audio)
        except Exception:
            self.logger.exception("Failed to send voice message to chat %s", chat_id)


async def setup_scheduler(
    bot: Bot,
    db: Database,
    gemini: GeminiClient,
    tts: TextToSpeechService,
    cron: str,
    tz: str,
) -> LessonScheduler:
    scheduler = LessonScheduler(bot, db, gemini, tts, default_cron=cron, timezone=tz)
    await scheduler.initialize()
    return scheduler
