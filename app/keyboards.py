from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


SET_TIME_BUTTON = "Настроить время"
GET_VERB_NOW_BUTTON = "Напомнить фразовый глагол"
GET_NEW_VERB_BUTTON = "Новый фразовый глагол"
AUDIO_DISABLE_BUTTON = "Отключить аудио"
AUDIO_ENABLE_BUTTON = "Включить аудио"
CANCEL_BUTTON = "Отмена"


def _base_menu_rows(send_audio: bool) -> list[list[KeyboardButton]]:
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text=SET_TIME_BUTTON),
            KeyboardButton(text=GET_VERB_NOW_BUTTON),
        ],
        [KeyboardButton(text=GET_NEW_VERB_BUTTON)],
    ]

    audio_button = KeyboardButton(
        text=AUDIO_DISABLE_BUTTON if send_audio else AUDIO_ENABLE_BUTTON,
    )
    rows.append([audio_button])
    return rows


def main_menu_keyboard(*, send_audio: bool) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=_base_menu_rows(send_audio),
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def time_settings_keyboard(*, send_audio: bool) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [[KeyboardButton(text=CANCEL_BUTTON)]]
    rows.extend(_base_menu_rows(send_audio))
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Введите время, например 09:30",
    )

