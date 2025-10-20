import asyncio
import logging

from aiogram import Router, types
from aiogram.dispatcher.event.bases import SkipHandler

from ..db import Database
from ..gemini import GeminiClient
from ..handlers.voice import send_voice_response
from ..keyboards import GET_NEW_VERB_BUTTON, GET_VERB_NOW_BUTTON, SET_TIME_BUTTON
from ..markdown import bold, escape
from ..tts import TextToSpeechService


router = Router(name=__name__)


logger = logging.getLogger("learn_en_bot.chat")


def setup(router_, db: Database, gemini: GeminiClient, tts: TextToSpeechService):
    async def _send_with_voice(
        message: types.Message,
        markdown_text: str,
        plain_text: str,
        *,
        send_audio: bool,
    ) -> None:
        await message.answer(markdown_text)
        if send_audio:
            await send_voice_response(
                message,
                plain_text,
                tts=tts,
                logger=logger,
                context="Gemini reply",
                audio_filename="gemini-response.wav",
            )

    # Любой текст: если есть сегодняшнее задание — оцениваем; иначе обычный ответ
    async def on_text(message: types.Message) -> None:
        text = (message.text or "").strip()
        if not text:
            return

        if text in {SET_TIME_BUTTON, GET_VERB_NOW_BUTTON, GET_NEW_VERB_BUTTON}:
            raise SkipHandler()

        tg_user = message.from_user
        db_user = None
        assgn = None
        if tg_user:
            db_user = await asyncio.to_thread(
                db.add_or_get_user, chat_id=tg_user.id, username=tg_user.username
            )
            assgn = db.get_today_assignment_by_chat(tg_user.id)

        send_audio = bool(db_user.send_audio) if db_user else True

        if assgn and assgn.status != "mastered":
            waiting = await message.answer(escape("Ожидаем ответа ..."))
            try:
                feedback, mastered = await asyncio.to_thread(
                    gemini.evaluate_usage, assgn.phrasal_verb, text
                )
            finally:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=waiting.message_id)
                except Exception:
                    pass

            if mastered:
                db.mark_mastered(assgn.id)
                success_plain = (
                    f"{feedback}\n\nОтлично! Задание на сегодня выполнено ✅"
                )
                success_markdown = (
                    f"{_safe_markdown(feedback)}\n\n"
                    f"{bold('Отлично!')} {escape('Задание на сегодня выполнено ✅')}"
                )
                await _send_with_voice(
                    message,
                    success_markdown,
                    success_plain,
                    send_audio=send_audio,
                )
            else:
                await _send_with_voice(
                    message,
                    _safe_markdown(feedback),
                    feedback,
                    send_audio=send_audio,
                )
            return

        waiting = await message.answer(escape("Ожидаем ответа ..."))
        try:
            reply = await asyncio.to_thread(
                gemini.generate,
                prompt=(
                    f"Пользователь задаёт вопрос: {text}\n"
                    "Ответь кратко по сути на русском, без приветствий, обращений и эмодзи."
                    " Верни простой текст без разметки."
                ),
                fallback="Пока не могу ответить. Попробуйте позже.",
            )
        finally:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=waiting.message_id)
            except Exception:
                pass
        plain_text = reply or "Пока не могу ответить. Попробуйте позже."
        await _send_with_voice(
            message,
            _safe_markdown(reply, fallback="Пока не могу ответить. Попробуйте позже."),
            plain_text,
            send_audio=send_audio,
        )

    router_.message.register(on_text)


def _safe_markdown(text: str, fallback: str | None = None) -> str:
    sanitized = escape(text)
    if sanitized:
        return sanitized

    if fallback:
        return escape(fallback)

    return escape(text)
