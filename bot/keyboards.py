from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_back_to_menu_kb():
    """Клавиатура с кнопкой возврата в меню"""
    kb = [
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_cancel_kb():
    kb = [
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_country_kb():
    """Клавиатура выбора страны"""
    kb = [
        [KeyboardButton(text="🇧🇾 Беларусь"), KeyboardButton(text="🇷🇺 Россия")],       
        [KeyboardButton(text="🇰🇿 Казахстан"), KeyboardButton(text="🇦🇲 Армения")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_user_type_kb():
    """Клавиатура выбора типа пользователя"""
    kb = [
        [KeyboardButton(text="👨‍⚕️ Ветеринарный врач клиники-партнера")],
        [KeyboardButton(text="🔬 Сотрудник X-LAB VET")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_specialization_kb():
    """Клавиатура выбора специализации для ветеринарных врачей"""
    kb = [
        [KeyboardButton(text="Нефрология"), KeyboardButton(text="Хирургия"), KeyboardButton(text="Терапия")],
        [KeyboardButton(text="Ортопедия"), KeyboardButton(text="Онкология"), KeyboardButton(text="Дерматология")], 
        [KeyboardButton(text="Стоматология"), KeyboardButton(text="Офтальмология")],
        [KeyboardButton(text="✏️ Ввести свою специализацию")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_region_kb_belarus():
    """Клавиатура выбора региона для Беларуси"""
    kb = [
        [KeyboardButton(text="📍 Минск"), KeyboardButton(text="📍 Минская область")],
        [KeyboardButton(text="📍 Брест"), KeyboardButton(text="📍 Брестская область")],
        [KeyboardButton(text="📍 Гомель"), KeyboardButton(text="📍 Гомельская область")],
        [KeyboardButton(text="📍 Гродно"), KeyboardButton(text="📍 Гродненская область")],
        [KeyboardButton(text="📍 Могилев"), KeyboardButton(text="📍 Могилевская область")],
        [KeyboardButton(text="📍 Витебск"), KeyboardButton(text="📍 Витебская область")],
        [KeyboardButton(text="✏️ Ввести свой регион")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_region_kb_russia():
    """Клавиатура выбора региона для России"""
    kb = [
        [KeyboardButton(text="📍 Москва"), KeyboardButton(text="📍 Московская область")],
        [KeyboardButton(text="📍 Санкт-Петербург"), KeyboardButton(text="📍 Ленинградская область")],
        [KeyboardButton(text="📍 Новосибирск"), KeyboardButton(text="📍 Екатеринбург")],
        [KeyboardButton(text="📍 Нижний Новгород"), KeyboardButton(text="📍 Казань")],
        [KeyboardButton(text="📍 Челябинск"), KeyboardButton(text="📍 Омск")],
        [KeyboardButton(text="📍 Самара"), KeyboardButton(text="📍 Ростов-на-Дону")],
        [KeyboardButton(text="📍 Уфа"), KeyboardButton(text="📍 Красноярск")],
        [KeyboardButton(text="✏️ Ввести свой регион")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_region_kb_kazakhstan():
    """Клавиатура выбора региона для Казахстана"""
    kb = [
        [KeyboardButton(text="📍 Алматы"), KeyboardButton(text="📍 Астана (Нур-Султан)")],
        [KeyboardButton(text="📍 Шымкент"), KeyboardButton(text="📍 Караганда")],
        [KeyboardButton(text="📍 Актобе"), KeyboardButton(text="📍 Павлодар")],
        [KeyboardButton(text="📍 Тараз"), KeyboardButton(text="📍 Усть-Каменогорск")],
        [KeyboardButton(text="📍 Семей"), KeyboardButton(text="📍 Атырау")],
        [KeyboardButton(text="📍 Костанай"), KeyboardButton(text="📍 Кызылорда")],
        [KeyboardButton(text="✏️ Ввести свой регион")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_region_kb_armenia():
    """Клавиатура выбора региона для Армении"""
    kb = [
        [KeyboardButton(text="📍 Ереван"), KeyboardButton(text="📍 Гюмри")],
        [KeyboardButton(text="📍 Ванадзор"), KeyboardButton(text="📍 Вагаршапат")],
        [KeyboardButton(text="📍 Абовян"), KeyboardButton(text="📍 Капан")],
        [KeyboardButton(text="📍 Раздан"), KeyboardButton(text="📍 Армавир")],
        [KeyboardButton(text="📍 Арташат"), KeyboardButton(text="📍 Севан")],
        [KeyboardButton(text="📍 Горис"), KeyboardButton(text="📍 Аштарак")],
        [KeyboardButton(text="✏️ Ввести свой регион")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_region_kb(country: str = 'BY'):
    """Получить клавиатуру региона по коду страны"""
    if country == 'BY':
        return get_region_kb_belarus()
    elif country == 'RU':
        return get_region_kb_russia()
    elif country == 'KZ':
        return get_region_kb_kazakhstan()
    elif country == 'AM':
        return get_region_kb_armenia()
    else:
        return get_region_kb_belarus()  # По умолчанию

def get_department_function_kb():
    """Клавиатура выбора функции сотрудника"""
    kb = [
        [KeyboardButton(text="🔬 Лаборатория")],
        [KeyboardButton(text="💰 Продажи")],
        [KeyboardButton(text="🤝 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_main_menu_kb():
    """Единое меню для всех пользователей (кроме админа)"""
    kb = [
        [KeyboardButton(text="🔬 Задать вопрос"), KeyboardButton(text="📋 Стоп-лист")],
        # [KeyboardButton(text="📚 Часто задаваемые вопросы")],
        [KeyboardButton(text="🖼️ Галерея пробирок"), KeyboardButton(text="📄 Скачать бланки")],
        [KeyboardButton(text="📞 Связь с лабораторией")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_menu_kb():
    """Меню для администраторов с логической группировкой"""
    kb = [
        # Аналитика
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📈 Экспорт метрик")],
        [KeyboardButton(text="📥 Выгрузка в Excel")],
        
        # Пользователи и коды
        [KeyboardButton(text="👥 Пользователи")],
        [KeyboardButton(text="🔐 Создать код"), KeyboardButton(text="🔑 Активировать код")],
        
        # Обращения и коммуникации
        [KeyboardButton(text="📋 Все обращения"), KeyboardButton(text="📋 Опросы")],
        [KeyboardButton(text="📢 Рассылка")],
        
        # Контент и система
        [KeyboardButton(text="⚙️ Управление стоп-листом")],
        [KeyboardButton(text="🎨 Управление контентом"), KeyboardButton(text="📚 Часто задаваемые вопросы")],
        [KeyboardButton(text="🔧 Управление системой")],
        
        # Основные функции
        [KeyboardButton(text="🔬 Задать вопрос")],
        [KeyboardButton(text="📋 Стоп-лист")],
        [KeyboardButton(text="🖼️ Галерея пробирок"), KeyboardButton(text="📄 Скачать бланки")],
        [KeyboardButton(text="📞 Связь с лабораторией")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_content_management_kb():
    """Клавиатура управления контентом"""
    keyboard = [
        [KeyboardButton(text="⚙️ Управление галереей")], 
        [KeyboardButton(text="⚙️ Управление бланками")], 
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_phone_kb():
    kb = [
        [KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_contact_type_kb():
    """Клавиатура выбора типа обращения для связи с лабораторией"""
    kb = [
        [KeyboardButton(text="📞 Заказать звонок")],
        [KeyboardButton(text="💡 Предложение/жалоба")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_feedback_type_kb():
    kb = [
        [KeyboardButton(text="💡 Предложение"), KeyboardButton(text="⚠️ Жалоба")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]      
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_menu_by_role(role: str):
    """Получить меню в зависимости от роли"""
    if role == 'admin':
        return get_admin_menu_kb()
    else:
        return get_main_menu_kb()
    
def get_dialog_kb():
    """Клавиатура для диалога с ассистентом"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Завершить диалог")]
        ],
        resize_keyboard=True
    )

def get_poll_in_progress_kb():
    """Клавиатура для режима прохождения опроса"""
    kb = [
        [KeyboardButton(text="❌ Выйти из опроса")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_excel_export_kb():
    """Клавиатура для выбора типа выгрузки"""
    kb = [
        [KeyboardButton(text="📊 Полная выгрузка")],
        [KeyboardButton(text="👥 Только пользователи")],
        [KeyboardButton(text="❓ Только вопросы")],
        [KeyboardButton(text="💬 История общения с ботом")],
        [KeyboardButton(text="📞 Только звонки")],
        [KeyboardButton(text="💡 Только обратная связь")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_broadcast_type_kb():
    """Клавиатура для выбора типа рассылки"""
    kb = [
        [KeyboardButton(text="📢 Всем пользователям")],
        [KeyboardButton(text="👨‍⚕️ Только клиентам")],
        [KeyboardButton(text="🔬 Только сотрудникам")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_system_management_kb():
    """Клавиатура управления системой"""
    kb = [
        [KeyboardButton(text="🔄 Обновить векторную БД")],
        [KeyboardButton(text="🗑️ Очистить старые логи")],
        [KeyboardButton(text="📊 Системная информация")],
        [KeyboardButton(text="🧪 Управление фото контейнеров")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_search_type_kb():
    """Клавиатура выбора типа поиска"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔢 Поиск по коду теста")],
            [KeyboardButton(text="📝 Поиск по названию")],
            [KeyboardButton(text="🔙 Вернуться в главное меню")]
        ],
        resize_keyboard=True
    )

def get_confirmation_kb():
    """Клавиатура для подтверждения типа поиска"""
    kb = [
        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")],
        [KeyboardButton(text="❌ Завершить диалог")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_search_type_clarification_kb():
    """Клавиатура для уточнения типа поиска"""
    kb = [
        [KeyboardButton(text="🔢 Поиск по коду теста")],
        [KeyboardButton(text="📝 Поиск по названию")],
        [KeyboardButton(text="❓ Общий вопрос")],
        [KeyboardButton(text="❌ Завершить диалог")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_faq_search_kb():
    """Клавиатура для поиска в FAQ"""
    kb = [
        [KeyboardButton(text="🔍 Поиск по базе знаний")],
        [KeyboardButton(text="📋 Показать все вопросы")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_faq_back_kb():
    """Клавиатура для возврата из FAQ"""
    kb = [
        [KeyboardButton(text="🔙 Назад к списку вопросов")],
        [KeyboardButton(text="🏠 В главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_search_type_switch_kb(search_id: str = "", tests_count: int = 0, profiles_count: int = 0, total_count: int = 0):
    """Клавиатура переключения между тестами и профилями"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🧪 Тесты ({tests_count})", callback_data=f"switch_view:tests:{search_id}"),
                InlineKeyboardButton(text=f"🔬 Профили ({profiles_count})", callback_data=f"switch_view:profiles:{search_id}")
            ],
            [
                InlineKeyboardButton(text=f"📋 Все результаты ({total_count})", callback_data=f"switch_view:all:{search_id}")
            ]
        ]
    )

# Для совместимости
get_client_menu_kb = get_main_menu_kb
get_staff_menu_kb = get_main_menu_kb
