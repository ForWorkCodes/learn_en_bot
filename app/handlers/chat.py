from aiogram import Router, types
from aiogram.filters import Command

from ..db import Database
from ..gemini import GeminiClient


router = Router(name=__name__)


def setup(router_, db: Database, gemini: GeminiClient):
    # Простая обработка любого текста — ответ от Gemini
    async def on_text(message: types.Message) -> None:
        text = (message.text or "").strip()
        if not text:
            return
        reply = gemini.generate(
            prompt=f"Пользователь спрашивает про английский: {text}\nОтветь по существу, кратко и дружелюбно на русском.",
            fallback="Пока не могу ответить. Попробуйте позже.",
        )
        await message.answer(reply)

    # Регистрируем AFTER командных хэндлеров
    router_.message.register(on_text)

