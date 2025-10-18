import asyncio
import logging

from aiogram import F, Router, types
from aiogram.filters import Command

from ..db import Database
from ..gemini import GeminiClient
from ..keyboards import (
    GET_NEW_VERB_BUTTON,
    GET_VERB_NOW_BUTTON,
    main_menu_keyboard,
)
from ..markdown import escape
from ..scheduler import LessonScheduler
from ..services.assignments import ensure_daily_assignment


logger = logging.getLogger("learn_en_bot.lesson")


router = Router(name=__name__)


def setup(router_: Router, db: Database, gemini: GeminiClient, scheduler: LessonScheduler) -> None:
    async def send_assignment(message: types.Message, *, force_new: bool) -> None:
        user = message.from_user
        if not user:
            await message.answer(escape("Попробуйте ещё раз"))
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )

        assignment, text, created = await ensure_daily_assignment(
            db, gemini, db_user, force_new=force_new
        )

        try:
            await message.answer(text, reply_markup=main_menu_keyboard())
        except Exception:
            chat = getattr(message, "chat", None)
            chat_id = getattr(chat, "id", None)
            logger.exception("Failed to send assignment message to chat %s", chat_id)
            return

        await asyncio.to_thread(db.mark_assignment_delivered, assignment.id)
        if created:
            scheduler.plan_followups(db_user.id, assignment.id)

    async def on_lesson(message: types.Message) -> None:
        await send_assignment(message, force_new=False)

    async def on_get_now(message: types.Message) -> None:
        await send_assignment(message, force_new=False)

    async def on_get_new(message: types.Message) -> None:
        await send_assignment(message, force_new=True)

    router_.message.register(on_lesson, Command("lesson"))
    router_.message.register(on_get_now, F.text == GET_VERB_NOW_BUTTON)
    router_.message.register(on_get_new, F.text == GET_NEW_VERB_BUTTON)

