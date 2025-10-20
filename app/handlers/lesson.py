import asyncio
import logging

from aiogram import F, Router, types
from aiogram.filters import Command

from ..db import Database
from ..gemini import GeminiClient
from ..handlers.voice import send_voice_response
from ..keyboards import (
    GET_NEW_VERB_BUTTON,
    GET_VERB_NOW_BUTTON,
    GET_NEW_VERB_CALLBACK,
    GET_VERB_NOW_CALLBACK,
    main_menu_keyboard,
)
from ..markdown import escape
from ..messages import FormattedMessage, format_assignment_reminder
from ..scheduler import LessonScheduler
from ..services.assignments import ensure_daily_assignment
from ..tts import TextToSpeechService


logger = logging.getLogger("learn_en_bot.lesson")


router = Router(name=__name__)


def setup(
    router_: Router,
    db: Database,
    gemini: GeminiClient,
    scheduler: LessonScheduler,
    tts: TextToSpeechService,
) -> None:
    async def _send_formatted_message(
        message: types.Message,
        formatted: FormattedMessage,
        *,
        reply_markup: types.InlineKeyboardMarkup | None = None,
        send_audio: bool,
    ) -> None:
        await message.answer(formatted.markdown, reply_markup=reply_markup)
        if send_audio:
            await send_voice_response(
                message,
                formatted.plain,
                tts=tts,
                logger=logger,
                context="assignment",
                audio_filename="assignment.wav",
            )

    async def send_assignment(
        message: types.Message,
        user: types.User,
        *,
        force_new: bool,
        reminder_only: bool = False,
    ) -> None:
        if not user:
            await message.answer(escape("Попробуйте ещё раз"))
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        send_audio = bool(db_user.send_audio)

        if reminder_only and not force_new:
            latest_assignment = await asyncio.to_thread(
                db.get_latest_assignment, db_user.id
            )
            if latest_assignment:
                text = format_assignment_reminder(
                    verb=latest_assignment.phrasal_verb,
                    translation=latest_assignment.translation,
                    explanation=latest_assignment.explanation,
                    examples_json=latest_assignment.examples_json,
                )
                try:
                    await _send_formatted_message(
                        message,
                        text,
                        reply_markup=main_menu_keyboard(send_audio=send_audio),
                        send_audio=send_audio,
                    )
                except Exception:
                    chat = getattr(message, "chat", None)
                    chat_id = getattr(chat, "id", None)
                    logger.exception(
                        "Failed to send reminder message to chat %s", chat_id
                    )
                    return

                await asyncio.to_thread(
                    db.mark_assignment_delivered, latest_assignment.id
                )
                return

        assignment, text, created = await ensure_daily_assignment(
            db, gemini, db_user, force_new=force_new
        )

        try:
            await _send_formatted_message(
                message,
                text,
                reply_markup=main_menu_keyboard(send_audio=send_audio),
                send_audio=send_audio,
            )
        except Exception:
            chat = getattr(message, "chat", None)
            chat_id = getattr(chat, "id", None)
            logger.exception("Failed to send assignment message to chat %s", chat_id)
            return

        await asyncio.to_thread(db.mark_assignment_delivered, assignment.id)
        if created:
            scheduler.plan_followups(db_user.id, assignment.id)

    async def on_lesson(message: types.Message) -> None:
        await send_assignment(message, message.from_user, force_new=False)

    async def on_get_now(message: types.Message) -> None:
        await send_assignment(message, message.from_user, force_new=False, reminder_only=True)

    async def on_get_new(message: types.Message) -> None:
        await send_assignment(message, message.from_user, force_new=True)

    async def on_get_now_callback(callback: types.CallbackQuery) -> None:
        await callback.answer()
        if not callback.message:
            return
        await send_assignment(
            callback.message,
            callback.from_user,
            force_new=False,
            reminder_only=True,
        )

    async def on_get_new_callback(callback: types.CallbackQuery) -> None:
        await callback.answer()
        if not callback.message:
            return
        await send_assignment(
            callback.message,
            callback.from_user,
            force_new=True,
        )

    router_.message.register(on_lesson, Command("lesson"))
    router_.message.register(on_get_now, F.text == GET_VERB_NOW_BUTTON)
    router_.message.register(on_get_new, F.text == GET_NEW_VERB_BUTTON)
    router_.callback_query.register(on_get_now_callback, F.data == GET_VERB_NOW_CALLBACK)
    router_.callback_query.register(on_get_new_callback, F.data == GET_NEW_VERB_CALLBACK)

