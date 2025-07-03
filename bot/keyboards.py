from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_cancel_kb():
    kb = [
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_user_type_kb():
    """Клавиатура выбора типа пользователя"""
    kb = [
        [KeyboardButton(text="👨‍⚕️ Ветеринарный врач клиники-партнера")],
        [KeyboardButton(text="👷 Сотрудник VET UNION")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_specialization_kb():
    """Клавиатура выбора специализации для ветеринарных врачей"""
    kb = [
        [KeyboardButton(text="🏥 Общая практика")],
        [KeyboardButton(text="💊 Терапевт"), KeyboardButton(text="🔪 Хирург")],
        [KeyboardButton(text="🔬 Лаборант"), KeyboardButton(text="🦷 Стоматолог")],
        [KeyboardButton(text="👁 Офтальмолог"), KeyboardButton(text="🧠 Невролог")],
        [KeyboardButton(text="🦴 Ортопед"), KeyboardButton(text="❤️ Кардиолог")],
        [KeyboardButton(text="✏️ Ввести свою специализацию")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_region_kb():
    """Клавиатура выбора региона для сотрудников"""
    kb = [
        [KeyboardButton(text="📍 Минск"), KeyboardButton(text="📍 Минская область")],
        [KeyboardButton(text="📍 Брест"), KeyboardButton(text="📍 Брестская область")],
        [KeyboardButton(text="📍 Витебск"), KeyboardButton(text="📍 Витебская область")],
        [KeyboardButton(text="📍 Гомель"), KeyboardButton(text="📍 Гомельская область")],
        [KeyboardButton(text="📍 Гродно"), KeyboardButton(text="📍 Гродненская область")],
        [KeyboardButton(text="📍 Могилёв"), KeyboardButton(text="📍 Могилёвская область")],
        [KeyboardButton(text="✏️ Ввести свой регион")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_department_function_kb():
    """Клавиатура выбора функции сотрудника"""
    kb = [
        [KeyboardButton(text="🔬 Лаборатория")],
        [KeyboardButton(text="💰 Продажи")],
        [KeyboardButton(text="🤝 Поддержка")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_main_menu_kb():
    """Единое меню для всех пользователей (кроме админа)"""
    kb = [
        [KeyboardButton(text="❓ Задать вопрос")],
        [KeyboardButton(text="📞 Обратная связь")],
        [KeyboardButton(text="💡 Предложения и пожелания")],
        [KeyboardButton(text="🔑 Активировать код")]
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
    else:
        return get_main_menu_kb()

# Для совместимости
get_client_menu_kb = get_main_menu_kb
get_staff_menu_kb = get_main_menu_kb