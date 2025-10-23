import asyncio
from typing import Awaitable, Callable

from aiogram import F, Router, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..db import Database
from ..keyboards import (
    AUDIO_DISABLE_BUTTON,
    AUDIO_ENABLE_BUTTON,
    GET_NEW_VERB_BUTTON,
    GET_VERB_NOW_BUTTON,
    UNSUBSCRIBE_BUTTON,
    SET_TIME_BUTTON,
    main_menu_keyboard,
    time_settings_keyboard,
)
from ..markdown import escape
from ..scheduler import LessonScheduler


router = Router(name=__name__)


class TimeSettings(StatesGroup):
    waiting_for_time = State()


UnsubscribeHandler = Callable[[types.Message, FSMContext | None], Awaitable[None]]


def setup(router_: Router, db: Database, scheduler: LessonScheduler) -> None:
    # Если нужно передать зависимости в хэндлеры — можно через замыкания или контекст
    unsubscribe = handle_unsubscribe(db, scheduler)

    router_.message.register(start_handler(db), CommandStart())
    router_.message.register(ping_handler, Command("ping"))
    router_.message.register(handle_set_time(db), F.text == SET_TIME_BUTTON)
    router_.message.register(unsubscribe, Command("unsubscribe"))
    router_.message.register(
        process_time_input(db, scheduler, unsubscribe),
        StateFilter(TimeSettings.waiting_for_time),
    )
    router_.message.register(
        toggle_audio_notifications(db),
        (F.text == AUDIO_ENABLE_BUTTON) | (F.text == AUDIO_DISABLE_BUTTON),
    )
    router_.message.register(unsubscribe, F.text == UNSUBSCRIBE_BUTTON)


def start_handler(db: Database):
    async def handler(message: types.Message) -> None:
        user = message.from_user
        if not user:
            await message.answer(
                escape("Здравствуйте!"),
                reply_markup=main_menu_keyboard(send_audio=True),
            )
            return
        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        await message.answer(
            escape(
                "Привет! Я помогу в изучении английского. Выберите действие на клавиатуре."
            ),
            reply_markup=main_menu_keyboard(send_audio=db_user.send_audio),
        )

    return handler


async def ping_handler(message: types.Message) -> None:
    await message.answer("pong")


def handle_set_time(db: Database):
    async def handler(message: types.Message, state: FSMContext) -> None:
        user = message.from_user
        if not user:
            await message.answer(escape("Не удалось определить пользователя. Попробуйте позже."))
            return
        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        await state.set_state(TimeSettings.waiting_for_time)
        await message.answer(
            escape("Введите время, когда отправлять глагол, в формате ЧЧ:ММ. Например: 09:30."),
            reply_markup=time_settings_keyboard(send_audio=db_user.send_audio),
        )

    return handler


def process_time_input(
    db: Database,
    scheduler: LessonScheduler,
    unsubscribe_handler: UnsubscribeHandler,
):
    async def handler(message: types.Message, state: FSMContext) -> None:
        text = (message.text or "").strip()

        if text.startswith("/"):
            return

        user = message.from_user
        db_user = None
        send_audio = True
        if user:
            db_user = await asyncio.to_thread(
                db.add_or_get_user, chat_id=user.id, username=user.username
            )
            send_audio = bool(db_user.send_audio)

        if text in {SET_TIME_BUTTON, GET_VERB_NOW_BUTTON, GET_NEW_VERB_BUTTON, UNSUBSCRIBE_BUTTON}:
            if text == UNSUBSCRIBE_BUTTON:
                await unsubscribe_handler(message, state)
                return
            await state.clear()
            await message.answer(
                escape("Настройку времени отменил. Выберите действие на клавиатуре."),
                reply_markup=main_menu_keyboard(send_audio=send_audio),
            )
            return

        if text in {AUDIO_DISABLE_BUTTON, AUDIO_ENABLE_BUTTON}:
            await toggle_audio_notifications(db)(message, state)
            return

        if text.lower() in {"cancel", "отмена"}:
            await state.clear()
            await message.answer(
                escape("Настройку времени отменил. Выберите действие на клавиатуре."),
                reply_markup=main_menu_keyboard(send_audio=send_audio),
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

        if not user:
            await state.clear()
            await message.answer(escape("Не удалось сохранить время. Попробуйте позже."))
            return

        if not db_user:
            db_user = await asyncio.to_thread(
                db.add_or_get_user, chat_id=user.id, username=user.username
            )
            send_audio = bool(db_user.send_audio)
        await asyncio.to_thread(
            db.update_user_daily_time,
            db_user.id,
            hour,
            minute,
            mark_subscribed=True,
        )
        await scheduler.reschedule_user(db_user.id)
        await state.clear()
        await message.answer(
            escape(f"Отлично! Буду присылать глагол каждый день в {hour:02d}:{minute:02d}."),
            reply_markup=main_menu_keyboard(send_audio=send_audio),
        )

    return handler


def handle_unsubscribe(db: Database, scheduler: LessonScheduler) -> UnsubscribeHandler:
    async def handler(message: types.Message, state: FSMContext | None = None) -> None:
        user = message.from_user
        if not user:
            if state:
                await state.clear()
            await message.answer(
                escape("Не удалось определить пользователя. Попробуйте позже."),
                reply_markup=main_menu_keyboard(send_audio=True),
            )
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        send_audio = bool(db_user.send_audio)

        await asyncio.to_thread(
            db.update_user_daily_time,
            db_user.id,
            None,
            None,
            mark_subscribed=False,
        )
        await scheduler.reschedule_user(db_user.id)

        if state:
            await state.clear()

        await message.answer(
            escape(
                "Больше не буду присылать уроки по расписанию. Если передумаете, нажмите «Время» и настройте напоминание заново."
            ),
            reply_markup=main_menu_keyboard(send_audio=send_audio),
        )

    return handler


def toggle_audio_notifications(db: Database):
    async def handler(message: types.Message, state: FSMContext | None = None) -> None:
        text = (message.text or "").strip()
        enable_audio = text == AUDIO_ENABLE_BUTTON
        disable_audio = text == AUDIO_DISABLE_BUTTON
        if not enable_audio and not disable_audio:
            return

        user = message.from_user
        if not user:
            if state:
                await state.clear()
            await message.answer(
                escape("Не удалось определить пользователя. Попробуйте позже."),
                reply_markup=main_menu_keyboard(send_audio=True),
            )
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        current_state = bool(db_user.send_audio)
        desired_state = enable_audio

        reply_markup = main_menu_keyboard(send_audio=desired_state)

        if desired_state == current_state:
            if state:
                await state.clear()
            await message.answer(
                escape(
                    "Голосовые уже {}.".format(
                        "включены" if desired_state else "отключены"
                    )
                ),
                reply_markup=reply_markup,
            )
            return

        await asyncio.to_thread(
            db.update_user_audio_preference, db_user.id, desired_state
        )

        if state:
            await state.clear()

        response_text = (
            "Голосовые ответы включены." if desired_state else "Голосовые ответы отключены."
        )
        await message.answer(
            escape(response_text),
            reply_markup=reply_markup,
        )

    return handler

