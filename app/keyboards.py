from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


SET_TIME_BUTTON = "Время"
GET_VERB_NOW_BUTTON = "Напомнить"
GET_NEW_VERB_BUTTON = "Новый"
AUDIO_DISABLE_BUTTON = "Аудио выкл"
AUDIO_ENABLE_BUTTON = "Аудио вкл"
UNSUBSCRIBE_BUTTON = "Отказаться от рассылки"
CANCEL_BUTTON = "Отмена"


def _base_menu_rows(send_audio: bool) -> list[list[KeyboardButton]]:
    buttons = [
        KeyboardButton(text=SET_TIME_BUTTON),
        KeyboardButton(text=GET_VERB_NOW_BUTTON),
        KeyboardButton(text=GET_NEW_VERB_BUTTON),
        KeyboardButton(text=AUDIO_DISABLE_BUTTON if send_audio else AUDIO_ENABLE_BUTTON),
        KeyboardButton(text=UNSUBSCRIBE_BUTTON),
    ]

    rows: list[list[KeyboardButton]] = []
    for index in range(0, len(buttons), 3):
        rows.append(buttons[index : index + 3])
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

