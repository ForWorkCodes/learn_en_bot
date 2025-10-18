import asyncio

from aiogram import Router, types

from ..db import Database
from ..gemini import GeminiClient
from ..markdown import bold, escape


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
                success_message = (
                    f"{_safe_markdown(feedback)}\n\n"
                    f"{bold('Отлично!')} {escape('Задание на сегодня выполнено ✅')}"
                )
                await message.answer(success_message)
            else:
                await message.answer(_safe_markdown(feedback))
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
        await message.answer(
            _safe_markdown(reply, fallback="Пока не могу ответить. Попробуйте позже.")
        )

    router_.message.register(on_text)


def _safe_markdown(text: str, fallback: str | None = None) -> str:
    sanitized = escape(text)
    if sanitized:
        return sanitized

    if fallback:
        return escape(fallback)

    return escape(text)
