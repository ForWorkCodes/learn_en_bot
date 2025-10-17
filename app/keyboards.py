from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


SET_TIME_BUTTON = "Установить время"
GET_VERB_NOW_BUTTON = "Получить глагол немедленно"
GET_NEW_VERB_BUTTON = "Получить новый глагол"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SET_TIME_BUTTON), KeyboardButton(text=GET_VERB_NOW_BUTTON)],
            [KeyboardButton(text=GET_NEW_VERB_BUTTON)],
        ],
        resize_keyboard=True,
    )
