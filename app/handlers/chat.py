import asyncio
from html import escape

from aiogram import Router, types

from ..db import Database
from ..gemini import GeminiClient
from ..html_utils import sanitize_html_fragment


router = Router(name=__name__)


def setup(router_, db: Database, gemini: GeminiClient):
    # Любой текст: если есть сегодняшнее задание — оцениваем; иначе обычный ответ
    async def on_text(message: types.Message) -> None:
        text = (message.text or "").strip()
        if not text:
            return

        tg_user = message.from_user
        assgn = None
        if tg_user:
            assgn = db.get_today_assignment_by_chat(tg_user.id)

        if assgn and assgn.status != "mastered":
            waiting = await message.answer("Ожидаем ответа ...")
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
                success_message = (
                    feedback + "\n<b>Отлично!</b> Задание на сегодня выполнено ✅"
                )
                await message.answer(_safe_html(success_message))
            else:
                await message.answer(_safe_html(feedback))
            return

        # Общий диалог: просим Gemini вернуть HTML-фрагмент вместо Markdown
        waiting = await message.answer("Ожидаем ответа ...")
        try:
            reply = await asyncio.to_thread(
                gemini.generate,
                prompt=(
                    f"Пользователь задаёт вопрос: {text}\n"
                    "Ответь кратко по сути на русском. Верни HTML-фрагмент без <html>/<body>,"
                    " используй только теги: b, i, u, s, code, pre, a, ul, ol, li, br."
                    " Не используй Markdown."
                ),
                fallback="Пока не могу ответить. Попробуйте позже.",
            )
        finally:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=waiting.message_id)
            except Exception:
                pass
        await message.answer(_safe_html(reply, fallback="Пока не могу ответить. Попробуйте позже."))

    router_.message.register(on_text)


def _safe_html(text: str, fallback: str | None = None) -> str:
    sanitized = sanitize_html_fragment(text)
    if sanitized:
        return sanitized

    if fallback:
        fallback_sanitized = sanitize_html_fragment(fallback)
        if fallback_sanitized:
            return fallback_sanitized
        return escape(fallback)

    return escape(text)
