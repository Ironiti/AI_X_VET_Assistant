import re
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import (
    get_user_type_kb, get_department_function_kb, 
    get_main_menu_kb, get_admin_menu_kb, get_specialization_kb,
    get_region_kb, get_country_kb
)
from bot.handlers.questions import (
    smart_test_search, format_test_data, format_test_info,
    fuzzy_test_search, format_similar_tests_with_links,
    QuestionStates, get_dialog_kb, normalize_test_code,
    reverse_translit  # Добавьте эту функцию
)
from src.data_vectorization import DataProcessor

from src.database.db_init import db

registration_router = Router()

async def get_tech_support_message():
    return (
        "🛠 Техничка VET UNION Assistant\n\n"
        "У вас возникли технические проблемы с ботом? Обнаружили ошибку или сбой в работе?\n\n"
        "Присоединяйтесь к нашей технической группе!\n\n"
        "📋 Данная группа предназначена для отправки ошибок в боте.\n\n"
        "🎯 Ваши сообщения об ошибках помогают:\n\n"
        "• Быстро устранять проблемы\n"
        "• Улучшать функционал бота\n"
        "• Делать сервис удобнее для всех\n\n"
        "💬 Как сообщить об ошибке:\n\n"
        "Укажите:\n"
        "• Ваш запрос - что именно вы спрашивали\n"
        "• Ответ бота - что ответил бот\n"
        "• Как должно быть - какой ответ ожидался\n\n"
        "👥 [Присоединиться к технической группе → https://t.me/+FUmjohiS_VQwNDIy]\n\n"
        "Вместе мы сделаем VET UNION Assistant лучше! ⚡️"
    )

class RegistrationStates(StatesGroup):
    waiting_for_user_type = State()
    waiting_for_country = State()
    # Для клиентов
    waiting_for_client_code = State()
    waiting_for_client_name = State()
    waiting_for_specialization = State()
    waiting_for_custom_specialization = State()
    # Для сотрудников
    waiting_for_region = State()
    waiting_for_custom_region = State()
    waiting_for_employee_name = State()
    waiting_for_department = State()

@registration_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} initiated registration")
    
    # Проверяем, есть ли параметры (deep link)
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("test_"):
        # Это deep link на тест
        encoded_code = args[1][5:]  # Убираем "test_"
        
        # Применяем обратную транслитерацию
        test_code = reverse_translit(encoded_code)
        
        print(f"[DEBUG] Received encoded: {encoded_code}")
        print(f"[DEBUG] After reverse translit: {test_code}")
        
        # Проверяем, зарегистрирован ли пользователь
        user_exists = await db.user_exists(user_id)
        
        if not user_exists:
            # Пользователь не зарегистрирован, сохраняем запрос теста и начинаем регистрацию
            await state.update_data(pending_test_code=test_code)
            await message.answer(
                "Для просмотра информации о тестах необходимо пройти регистрацию.\n\n"
                "После регистрации вы автоматически получите информацию о запрошенном тесте.\n\n"
                "Выберите, кто вы:",
                reply_markup=get_user_type_kb()
            )
            await state.set_state(RegistrationStates.waiting_for_user_type)
            return
        
        # Пользователь зарегистрирован, обрабатываем запрос теста
        await state.clear()  # Очищаем состояние на всякий случай
        
        loading_msg = await message.answer(f"🔍 Загружаю информацию о тесте {test_code}...")
        
        try:
            processor = DataProcessor()
            processor.load_vector_store()
            
            # Используем smart_test_search для поиска
            result, found_variant, match_type = await smart_test_search(processor, test_code)
            
            if result:
                doc = result[0]
                test_data = format_test_data(doc.metadata)
                
                # Удаляем сообщение о загрузке
                try:
                    await loading_msg.delete()
                except:
                    pass
                
                # Показываем информацию о тесте
                response = format_test_info(test_data)
                
                # Ищем похожие тесты
                similar_tests = await fuzzy_test_search(processor, test_data['test_code'], threshold=40)
                similar_tests = [(d, s) for d, s in similar_tests if d.metadata.get('test_code') != test_data['test_code']]
                
                # Добавляем похожие тесты с кликабельными ссылками
                if similar_tests:
                    response += format_similar_tests_with_links(similar_tests[:5])
                
                await message.answer(response, parse_mode="HTML", disable_web_page_preview=True)
                
                # Обновляем статистику
                await db.add_search_history(
                    user_id=user_id,
                    search_query=f"Deep link: {test_code}",
                    found_test_code=test_data['test_code'],
                    search_type='code',
                    success=True
                )
                await db.update_user_frequent_test(
                    user_id=user_id,
                    test_code=test_data['test_code'],
                    test_name=test_data['test_name']
                )
                
                # Устанавливаем контекст для диалога
                await state.set_state(QuestionStates.in_dialog)
                await state.update_data(current_test=test_data, last_viewed_test=test_data['test_code'])
                
                # Показываем клавиатуру диалога
                await message.answer(
                    "Можете задать вопрос об этом тесте или выбрать действие:",
                    reply_markup=get_dialog_kb()
                )
            else:
                try:
                    await loading_msg.delete()
                except:
                    pass
                    
                await message.answer(f"❌ Тест {test_code} не найден в базе данных")
                
                # Показываем главное меню
                user = await db.get_user(user_id)
                menu_kb = get_admin_menu_kb() if user['role'] == 'admin' else get_main_menu_kb()
                await message.answer(
                    "Выберите действие:",
                    reply_markup=menu_kb
                )
                
        except Exception as e:
            print(f"[ERROR] Deep link handling failed: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                await loading_msg.delete()
            except:
                pass
                
            await message.answer("⚠️ Ошибка при загрузке информации о тесте")
            
            # Показываем главное меню
            user = await db.get_user(user_id)
            menu_kb = get_admin_menu_kb() if user['role'] == 'admin' else get_main_menu_kb()
            await message.answer(
                "Выберите действие:",
                reply_markup=menu_kb
            )
        
        return  # Важно! Выходим, чтобы не выполнять обычную логику /start

    # Обычная логика /start (без deep link)
    await state.clear()
    user_exists = await db.user_exists(user_id)

    if user_exists:
        print(f"[INFO] User {user_id} already registered")
        user = await db.get_user(user_id)
        menu_kb = get_admin_menu_kb() if user['role'] == 'admin' else get_main_menu_kb()
        await message.answer(
            "Вы уже зарегистрированы! 🎉\n"
            "Используйте меню для дальнейшей работы.",
            reply_markup=menu_kb
        )
    else:
        print(f"[INFO] User {user_id} starting new registration")
        await message.answer(
            "Добро пожаловать в бот Лаборатории VET UNION! 🧪\n\n"
            "Для начала работы необходимо пройти регистрацию.\n"
            "Выберите, кто вы:",
            reply_markup=get_user_type_kb()
        )
        await state.set_state(RegistrationStates.waiting_for_user_type)

@registration_router.message(RegistrationStates.waiting_for_user_type)
async def process_user_type(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text == "👨‍⚕️ Ветеринарный врач клиники-партнера":
        await state.update_data(user_type='client')
    elif message.text == "🔬 Сотрудник VET UNION":
        await state.update_data(user_type='employee')
    else:
        await message.answer(
            "❌ Пожалуйста, выберите из предложенных вариантов",
            reply_markup=get_user_type_kb()
        )
        return
    
    # Переходим к выбору страны
    await message.answer(
        "🌍 В какой стране вы находитесь?",
        reply_markup=get_country_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_country)
    
@registration_router.message(RegistrationStates.waiting_for_country)
async def process_country(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    country_map = {
        "🇧🇾 Беларусь": "BY",
        "🇷🇺 Россия": "RU",
        "🇰🇿 Казахстан": "KZ",
        "🇦🇲 Армения": "AM"
    }
    
    if message.text not in country_map:
        await message.answer(
            "❌ Пожалуйста, выберите страну из предложенных вариантов",
            reply_markup=get_country_kb()
        )
        return
    
    country = country_map[message.text]
    await state.update_data(country=country)
    
    # Продолжаем в зависимости от типа пользователя
    data = await state.get_data()
    
    if data['user_type'] == 'client':
        await message.answer(
            "📝 Регистрация ветеринарного врача\n\n"
            "Введите ваш код клиники:\n"
            "⚠️ Код должен начинаться с 'В+' (например: В+КРАСАВЧИК)\n"
            "💡 Код клиники вы можете получить у представителя VET UNION",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationStates.waiting_for_client_code)
    else:
        # Для сотрудников показываем регионы выбранной страны
        await message.answer(
            "📝 Регистрация сотрудника VET UNION\n\n"
            "Выберите ваш регион:",
            reply_markup=get_region_kb(country)
        )
        await state.set_state(RegistrationStates.waiting_for_region)

# Обработчики для клиентов
@registration_router.message(RegistrationStates.waiting_for_client_code)
async def process_client_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip().upper()

    if len(code) < 3 or len(code) > 20 or not re.match(r'^[ВB]\+[А-ЯA-Z0-9\-]+$', code):
        await message.answer(
            "❌ Неверный формат кода клиники.\n\n"
            "Код должен:\n"
            "• Начинаться с 'В+'\n"
            "• Содержать только заглавные буквы и цифры\n"
            "• Пример: В+КРАСАВЧИК\n\n"
            "Попробуйте еще раз:"
        )
        return

    await state.update_data(client_code=code)
    await message.answer(
        f"✅ Код клиники: {code}\n\n"
        "Теперь введите ваше имя:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_client_name)

@registration_router.message(RegistrationStates.waiting_for_client_name)
async def process_client_name(message: Message, state: FSMContext):
    name = message.text.strip()

    if len(name) < 2 or len(name) > 50:
        await message.answer(
            "❌ Имя должно содержать от 2 до 50 символов.\nПопробуйте еще раз:"
        )
        return

    await state.update_data(name=name)
    await message.answer(
        f"👤 Имя: {name}\n\n"
        "Выберите вашу специализацию:",
        reply_markup=get_specialization_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_specialization)

@registration_router.message(RegistrationStates.waiting_for_specialization)
async def process_specialization(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text == "✏️ Ввести свою специализацию":
        await message.answer(
            "Введите вашу специализацию:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationStates.waiting_for_custom_specialization)
        return
    
    specialization_map = {
        "Нефрология": "Нефрология",
        "Хирургия": "Хирургия",
        "Терапия": "Терапия",
        "Ортопедия": "Ортопедия",
        "Онкология": "Онкология",
        "Дерматология": "Дерматология",
        "Офтальмология": "Офтальмология",
        "Стоматология": "Стоматология"
    }
    
    if message.text not in specialization_map:
        await message.answer(
            "❌ Пожалуйста, выберите специализацию из списка или введите свою",
            reply_markup=get_specialization_kb()
        )
        return
    
    specialization = specialization_map[message.text]
    data = await state.get_data()
    
    success = await db.add_client(
        telegram_id=user_id,
        name=data['name'],
        client_code=data['client_code'],
        specialization=specialization,
        country=data.get('country', 'BY')
    )

    if success:
        await message.answer(await get_tech_support_message())
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 Имя: {data['name']}\n"
            f"🏥 Код клиники: {data['client_code']}\n"
            f"📋 Специализация: {specialization}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка регистрации. Возможно, вы уже зарегистрированы.\nПопробуйте еще раз: /start",
            reply_markup=ReplyKeyboardRemove()
        )

    await state.clear()

@registration_router.message(RegistrationStates.waiting_for_custom_specialization)
async def process_custom_specialization(message: Message, state: FSMContext):
    user_id = message.from_user.id
    specialization = message.text.strip()

    if len(specialization) < 2 or len(specialization) > 100:
        await message.answer(
            "❌ Специализация должна содержать от 2 до 100 символов.\nПопробуйте еще раз:"
        )
        return

    data = await state.get_data()
    
    success = await db.add_client(
        telegram_id=user_id,
        name=data['name'],
        client_code=data['client_code'],
        specialization=specialization,
        country=data.get('country', 'BY')
    )

    if success:
        await message.answer(await get_tech_support_message())
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 Имя: {data['name']}\n"
            f"🏥 Код клиники: {data['client_code']}\n"
            f"📋 Специализация: {specialization}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка регистрации. Возможно, вы уже зарегистрированы.\nПопробуйте еще раз: /start",
            reply_markup=ReplyKeyboardRemove()
        )

    await state.clear()

# Обработчики для сотрудников
@registration_router.message(RegistrationStates.waiting_for_region)
async def process_region(message: Message, state: FSMContext):
    if message.text == "✏️ Ввести свой регион":
        await message.answer(
            "Введите ваш регион:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationStates.waiting_for_custom_region)
        return
    
    # Получаем данные из state
    data = await state.get_data()
    
    # Проверяем, что выбран регион из клавиатуры
    if not message.text.startswith("📍"):
        await message.answer(
            "❌ Пожалуйста, выберите регион из списка или введите свой",
            reply_markup=get_region_kb(data.get('country', 'BY'))
        )
        return
    
    region = message.text.replace("📍 ", "")
    await state.update_data(region=region)
    await message.answer(
        f"📍 Регион: {region}\n\n"
        "Введите вашу фамилию и имя:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_employee_name)

@registration_router.message(RegistrationStates.waiting_for_custom_region)
async def process_custom_region(message: Message, state: FSMContext):
    region = message.text.strip()

    if len(region) < 2 or len(region) > 100:
        await message.answer(
            "❌ Регион должен содержать от 2 до 100 символов.\nПопробуйте еще раз:"
        )
        return

    await state.update_data(region=region)
    await message.answer(
        f"📍 Регион: {region}\n\n"
        "Введите вашу фамилию и имя:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_employee_name)

@registration_router.message(RegistrationStates.waiting_for_employee_name)
async def process_employee_name(message: Message, state: FSMContext):
    name = message.text.strip()

    if len(name) < 3 or len(name) > 100:
        await message.answer(
            "❌ Фамилия и имя должно содержать от 3 до 100 символов.\nПопробуйте еще раз:"
        )
        return

    await state.update_data(name=name)
    await message.answer(
        f"👤 {name}\n\n"
        "Выберите функцию, которую вы исполняете:",
        reply_markup=get_department_function_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_department)

@registration_router.message(RegistrationStates.waiting_for_department)
async def process_department(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    department_map = {
        "🔬 Лаборатория": "laboratory",
        "💰 Продажи": "sales",
        "🤝 Поддержка": "support"
    }

    if message.text not in department_map:
        await message.answer(
            "❌ Пожалуйста, выберите функцию из предложенных вариантов",
            reply_markup=get_department_function_kb()
        )
        return

    data = await state.get_data()
    
    success = await db.add_employee(
        telegram_id=user_id,
        name=data['name'],
        region=data['region'],
        department_function=department_map[message.text],
        country=data['country']
    )

    if success:
        await message.answer(await get_tech_support_message())
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 {data['name']}\n"
            f"📍 Регион: {data['region']}\n"
            f"🏢 Функция: {message.text}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка регистрации. Попробуйте еще раз: /start",
            reply_markup=ReplyKeyboardRemove()
        )

    await state.clear()
