from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


SET_TIME_BUTTON = "Настроить время"
GET_VERB_NOW_BUTTON = "Напомнить фразовый глагол"
GET_NEW_VERB_BUTTON = "Новый фразовый глагол"
AUDIO_DISABLE_BUTTON = "Отключить аудио"
AUDIO_ENABLE_BUTTON = "Включить аудио"
CANCEL_BUTTON = "Отмена"

SET_TIME_CALLBACK = "menu:set_time"
GET_VERB_NOW_CALLBACK = "menu:get_now"
GET_NEW_VERB_CALLBACK = "menu:get_new"
DISABLE_AUDIO_CALLBACK = "menu:audio_off"
ENABLE_AUDIO_CALLBACK = "menu:audio_on"
CANCEL_TIME_CALLBACK = "menu:cancel_time"


def _base_menu_rows(send_audio: bool) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=SET_TIME_BUTTON, callback_data=SET_TIME_CALLBACK),
            InlineKeyboardButton(text=GET_VERB_NOW_BUTTON, callback_data=GET_VERB_NOW_CALLBACK),
        ],
        [InlineKeyboardButton(text=GET_NEW_VERB_BUTTON, callback_data=GET_NEW_VERB_CALLBACK)],
    ]

    audio_button = InlineKeyboardButton(
        text=AUDIO_DISABLE_BUTTON if send_audio else AUDIO_ENABLE_BUTTON,
        callback_data=DISABLE_AUDIO_CALLBACK if send_audio else ENABLE_AUDIO_CALLBACK,
    )
    rows.append([audio_button])
    return rows


def main_menu_keyboard(*, send_audio: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=_base_menu_rows(send_audio))


def time_settings_keyboard(*, send_audio: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=CANCEL_BUTTON, callback_data=CANCEL_TIME_CALLBACK)]]
    rows.extend(_base_menu_rows(send_audio))
    return InlineKeyboardMarkup(inline_keyboard=rows)

