from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command

from ..db import Database


router = Router(name=__name__)


def setup(router_: Router, db: Database) -> None:
    # Если нужно передать зависимости в хэндлеры — можно через замыкания или контекст
    router_.message.register(start_handler(db), CommandStart())
    router_.message.register(ping_handler, Command("ping"))


def start_handler(db: Database):
    async def handler(message: types.Message) -> None:
        user = message.from_user
        if not user:
            await message.answer("Здравствуйте!")
            return
        db.add_or_get_user(chat_id=user.id, username=user.username)
        await message.answer("Привет! Я помогу в изучении английского. Напиши мне вопрос или жди совет дня.")

    return handler


async def ping_handler(message: types.Message) -> None:
    await message.answer("pong")

