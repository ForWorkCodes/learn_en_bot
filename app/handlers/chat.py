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
                await message.answer(feedback + "\n<b>Отлично!</b> Задание на сегодня выполнено ✅")
            else:
                await message.answer(feedback)
            return

        # Общий диалог: просим Gemini вернуть HTML-фрагмент вместо Markdown
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
        await message.answer(reply)

    router_.message.register(on_text)

