import asyncio

from aiogram import F, Router, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..db import Database
from ..keyboards import (
    GET_NEW_VERB_BUTTON,
    GET_VERB_NOW_BUTTON,
    SET_TIME_BUTTON,
    main_menu_keyboard,
)
from ..markdown import escape
from ..scheduler import LessonScheduler


router = Router(name=__name__)


class TimeSettings(StatesGroup):
    waiting_for_time = State()


def setup(router_: Router, db: Database, scheduler: LessonScheduler) -> None:
    # Если нужно передать зависимости в хэндлеры — можно через замыкания или контекст
    router_.message.register(start_handler(db), CommandStart())
    router_.message.register(ping_handler, Command("ping"))
    router_.message.register(handle_set_time(db, scheduler), F.text == SET_TIME_BUTTON)
    router_.message.register(
        process_time_input(db, scheduler),
        StateFilter(TimeSettings.waiting_for_time),
    )


def start_handler(db: Database):
    async def handler(message: types.Message) -> None:
        user = message.from_user
        if not user:
            await message.answer(escape("Здравствуйте!"), reply_markup=main_menu_keyboard())
            return
        await asyncio.to_thread(db.add_or_get_user, chat_id=user.id, username=user.username)
        await message.answer(
            escape(
                "Привет! Я помогу в изучении английского. Выберите действие на клавиатуре."
            ),
            reply_markup=main_menu_keyboard(),
        )

    return handler


async def ping_handler(message: types.Message) -> None:
    await message.answer("pong")


def handle_set_time(db: Database, scheduler: LessonScheduler):
    async def handler(message: types.Message, state: FSMContext) -> None:
        user = message.from_user
        if not user:
            await message.answer(escape("Не удалось определить пользователя. Попробуйте позже."))
            return
        await asyncio.to_thread(db.add_or_get_user, chat_id=user.id, username=user.username)
        await state.set_state(TimeSettings.waiting_for_time)
        await message.answer(
            escape("Введите время, когда отправлять глагол, в формате ЧЧ:ММ. Например: 09:30."),
            reply_markup=main_menu_keyboard(),
        )

    return handler


def process_time_input(db: Database, scheduler: LessonScheduler):
    async def handler(message: types.Message, state: FSMContext) -> None:
        text = (message.text or "").strip()

        if text in {SET_TIME_BUTTON, GET_VERB_NOW_BUTTON, GET_NEW_VERB_BUTTON}:
            await state.clear()
            await message.answer(
                escape("Настройку времени отменил. Выберите действие на клавиатуре."),
                reply_markup=main_menu_keyboard(),
            )
            return

        parts = text.split(":", maxsplit=1)
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            await message.answer(escape("Не получилось распознать время. Напишите, например, 08:30."))
            return

        hour, minute = (int(parts[0]), int(parts[1]))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await message.answer(escape("Часы должны быть от 00 до 23, минуты — от 00 до 59."))
            return

        user = message.from_user
        if not user:
            await state.clear()
            await message.answer(escape("Не удалось сохранить время. Попробуйте позже."))
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        await asyncio.to_thread(db.update_user_daily_time, db_user.id, hour, minute)
        await scheduler.reschedule_user(db_user.id)
        await state.clear()
        await message.answer(
            escape(f"Отлично! Буду присылать глагол каждый день в {hour:02d}:{minute:02d}."),
            reply_markup=main_menu_keyboard(),
        )

    return handler

