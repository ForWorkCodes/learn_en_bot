import asyncio

from aiogram import Router, types

from ..db import Database
from ..gemini import GeminiClient


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
            feedback, mastered = await asyncio.to_thread(
                gemini.evaluate_usage, assgn.phrasal_verb, text
            )
            if mastered:
                db.mark_mastered(assgn.id)
                await message.answer(feedback + "\nОтлично! Задание на сегодня выполнено ✅")
            else:
                await message.answer(feedback)
            return

        # Фоллбек на общий диалог
        reply = await asyncio.to_thread(
            gemini.generate,
            prompt=(
                f"Пользователь спрашивает про английский: {text}\n"
                "Ответь по существу, кратко и дружелюбно на русском."
            ),
            fallback="Пока не могу ответить. Попробуйте позже.",
        )
        await message.answer(reply)

    # Регистрируем AFTER командных хэндлеров
    router_.message.register(on_text)

