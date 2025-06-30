from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_cancel_kb():
    kb = [
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_country_kb():
    kb = [
        [KeyboardButton(text="🇷🇺 Россия")],
        [KeyboardButton(text="🇧🇾 Беларусь")],
        [KeyboardButton(text="🇰🇿 Казахстан")],
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

def get_client_menu_kb():
    """Меню для обычных клиентов"""
    kb = [
        [KeyboardButton(text="❓ Задать вопрос")],
        [KeyboardButton(text="📞 Обратная связь")],
        [KeyboardButton(text="💡 Предложения и пожелания")],
        [KeyboardButton(text="🔑 Активировать код")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_staff_menu_kb():
    """Меню для сотрудников"""
    kb = [
        [KeyboardButton(text="🤖 Вопрос нейросети")],
        [KeyboardButton(text="👤 Мой профиль")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_menu_kb():
    """Меню для администраторов"""
    kb = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Пользователи")],
        [KeyboardButton(text="📋 Все обращения"), KeyboardButton(text="🔐 Создать код")],
        [KeyboardButton(text="❓ Задать вопрос"), KeyboardButton(text="📞 Обратная связь")],
        [KeyboardButton(text="💡 Предложения и пожелания")],
        [KeyboardButton(text="🔧 Управление системой")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_phone_kb():
    kb = [
        [KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_feedback_type_kb():
    kb = [
        [KeyboardButton(text="💡 Предложение"), KeyboardButton(text="⚠️ Жалоба")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_menu_by_role(role: str):
    """Получить меню в зависимости от роли"""
    if role == 'admin':
        return get_admin_menu_kb()
    elif role == 'staff':
        return get_staff_menu_kb()
    else:
        return get_client_menu_kb()

# Для обратной совместимости
get_main_menu_kb = get_client_menu_kb
