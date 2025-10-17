import asyncio
import json
from aiogram import Router, types
from aiogram.filters import Command

from ..db import Database
from ..gemini import GeminiClient


router = Router(name=__name__)


def format_assignment(verb: str, translation: str, explanation: str, examples_json: str) -> str:
    text = (
        f"Твой фразовый глагол дня: {verb} — {translation}\n"
        f"Пояснение: {explanation}\n\n"
        f"Примеры:\n"
    )
    try:
        examples = json.loads(examples_json)
    except Exception:
        examples = []
    for ex in examples:
        text += f"• {ex}\n"
    text += "\nНапиши предложение с этим глаголом. Я помогу исправить и объяснить."
    return text


def setup(router_: Router, db: Database, gemini: GeminiClient) -> None:
    async def on_lesson(message: types.Message) -> None:
        user = message.from_user
        if not user:
            await message.answer("Попробуйте ещё раз")
            return

        # Ensure user in DB
        u = db.add_or_get_user(chat_id=user.id, username=user.username)

        # Generate or get today's assignment
        data = await asyncio.to_thread(
            gemini.generate_phrasal_verb, user_hint=user.username or str(user.id)
        )
        assgn = db.ensure_today_assignment(
            u,
            verb=data["verb"],
            translation=data["translation"],
            explanation=data["explanation"],
            examples_json=json.dumps(data.get("examples", []), ensure_ascii=False),
        )
        await message.answer(
            format_assignment(assgn.phrasal_verb, assgn.translation, assgn.explanation, assgn.examples_json)
        )

    router_.message.register(on_lesson, Command("lesson"))

