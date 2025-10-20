import asyncio

from aiogram import F, Router, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..db import Database
from ..keyboards import (
    CANCEL_TIME_CALLBACK,
    DISABLE_AUDIO_CALLBACK,
    ENABLE_AUDIO_CALLBACK,
    GET_NEW_VERB_BUTTON,
    GET_VERB_NOW_BUTTON,
    SET_TIME_BUTTON,
    SET_TIME_CALLBACK,
    main_menu_keyboard,
    time_settings_keyboard,
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
    router_.message.register(handle_set_time(db), F.text == SET_TIME_BUTTON)
    router_.callback_query.register(handle_set_time_callback(db), F.data == SET_TIME_CALLBACK)
    router_.message.register(
        process_time_input(db, scheduler),
        StateFilter(TimeSettings.waiting_for_time),
    )
    router_.callback_query.register(
        cancel_time_configuration(db),
        StateFilter(TimeSettings.waiting_for_time),
        F.data == CANCEL_TIME_CALLBACK,
    )
    router_.callback_query.register(
        toggle_audio_notifications(db),
        (F.data == ENABLE_AUDIO_CALLBACK) | (F.data == DISABLE_AUDIO_CALLBACK),
    )


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


def handle_set_time_callback(db: Database):
    async def handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        user = callback.from_user
        message = callback.message
        if not user or not message:
            await callback.answer()
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        await state.set_state(TimeSettings.waiting_for_time)
        await callback.answer()
        await message.answer(
            escape("Введите время, когда отправлять глагол, в формате ЧЧ:ММ. Например: 09:30."),
            reply_markup=time_settings_keyboard(send_audio=db_user.send_audio),
        )

    return handler


def process_time_input(db: Database, scheduler: LessonScheduler):
    async def handler(message: types.Message, state: FSMContext) -> None:
        text = (message.text or "").strip()

        user = message.from_user
        db_user = None
        send_audio = True
        if user:
            db_user = await asyncio.to_thread(
                db.add_or_get_user, chat_id=user.id, username=user.username
            )
            send_audio = bool(db_user.send_audio)

        if text in {SET_TIME_BUTTON, GET_VERB_NOW_BUTTON, GET_NEW_VERB_BUTTON}:
            await state.clear()
            await message.answer(
                escape("Настройку времени отменил. Выберите действие на клавиатуре."),
                reply_markup=main_menu_keyboard(send_audio=send_audio),
            )
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
        await asyncio.to_thread(db.update_user_daily_time, db_user.id, hour, minute)
        await scheduler.reschedule_user(db_user.id)
        await state.clear()
        await message.answer(
            escape(f"Отлично! Буду присылать глагол каждый день в {hour:02d}:{minute:02d}."),
            reply_markup=main_menu_keyboard(send_audio=send_audio),
        )

    return handler


def cancel_time_configuration(db: Database):
    async def handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        user = callback.from_user
        message = callback.message
        if not user or not message:
            await callback.answer()
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        await state.clear()
        await callback.answer("Настройка отменена")
        await message.answer(
            escape("Настройку времени отменил. Выберите действие на клавиатуре."),
            reply_markup=main_menu_keyboard(send_audio=db_user.send_audio),
        )

    return handler


def toggle_audio_notifications(db: Database):
    async def handler(callback: types.CallbackQuery) -> None:
        user = callback.from_user
        message = callback.message
        if not user or not message:
            await callback.answer()
            return

        db_user = await asyncio.to_thread(
            db.add_or_get_user, chat_id=user.id, username=user.username
        )
        enable_audio = callback.data == ENABLE_AUDIO_CALLBACK
        disable_audio = callback.data == DISABLE_AUDIO_CALLBACK
        if not enable_audio and not disable_audio:
            await callback.answer()
            return

        current_state = bool(db_user.send_audio)
        desired_state = enable_audio
        if desired_state == current_state:
            await callback.answer(
                "Голосовые уже {}.".format(
                    "включены" if desired_state else "отключены"
                )
            )
            try:
                await message.edit_reply_markup(
                    reply_markup=main_menu_keyboard(send_audio=desired_state)
                )
            except Exception:
                pass
            return

        await asyncio.to_thread(
            db.update_user_audio_preference, db_user.id, desired_state
        )

        response_text = (
            "Голосовые ответы включены." if desired_state else "Голосовые ответы отключены."
        )
        reply_markup = main_menu_keyboard(send_audio=desired_state)
        try:
            await message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            await message.answer(
                escape("Обновил настройки клавиатуры."), reply_markup=reply_markup
            )

        await callback.answer(response_text)

    return handler

