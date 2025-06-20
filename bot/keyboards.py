from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_cancel_kb():
    kb = [
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_pet_type_kb():
    kb = [
        [KeyboardButton(text="🐕 Собака"), KeyboardButton(text="🐈 Кошка")],
        [KeyboardButton(text="🐰 Кролик"), KeyboardButton(text="🦜 Птица")],
        [KeyboardButton(text="🐹 Грызун"), KeyboardButton(text="🦎 Рептилия")],
        [KeyboardButton(text="Другое")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_main_menu_kb():
    kb = [
        [KeyboardButton(text="📅 Записаться на прием")],
        [KeyboardButton(text="💊 Мои рецепты"), KeyboardButton(text="📋 История визитов")],
        [KeyboardButton(text="❓ Задать вопрос"), KeyboardButton(text="📞 Заказать звонок")],
        [KeyboardButton(text="ℹ️ О клинике"), KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_phone_kb():
    kb = [
        [KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
