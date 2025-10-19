from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


SET_TIME_BUTTON = "Настроить время"
GET_VERB_NOW_BUTTON = "Напомнить фразовый глагол"
GET_NEW_VERB_BUTTON = "Новый фразовый глагол"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SET_TIME_BUTTON), KeyboardButton(text=GET_VERB_NOW_BUTTON)],
            [KeyboardButton(text=GET_NEW_VERB_BUTTON)],
        ],
        resize_keyboard=True,
    )

