import re
from aiogram import Router
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import (
    get_user_type_kb, get_department_function_kb, 
    get_main_menu_kb, get_admin_menu_kb, get_specialization_kb,
    get_region_kb, get_country_kb
)
from bot.handlers.questions import (
    smart_test_search, 
    format_test_data, format_test_info,
    fuzzy_test_search, 
    QuestionStates, get_dialog_kb, send_test_info_with_photo,
    # format_similar_tests_with_links,
)
from bot.handlers.utils import decode_test_code_from_url 
from src.data_vectorization import DataProcessor
from src.database.db_init import db

registration_router = Router()

# async def get_tech_support_message():
#     return (
#         "🛠 Техничка VET UNION Assistant\n\n"
#         "Отдельный чат техподдержки\n\n"
#         "📋 Данная группа предназначена для отправки ошибок в боте.\n\n"
#         "🎯 Ваши сообщения об ошибках помогают:\n\n"
#         "• Быстро устранять проблемы\n"
#         "• Улучшать функционал бота\n"
#         "• Делать сервис удобнее для всех\n\n"
#         "💬 Как сообщить об ошибке:\n\n"
#         "Укажите:\n"
#         "• Ваш запрос - что именно вы спрашивали\n"
#         "• Ответ бота - что ответил бот\n"
#         "• Как должно быть - какой ответ ожидался\n\n"
#         "👥 [Присоединиться к технической группе → https://t.me/+FUmjohiS_VQwNDIy]\n\n"
#         "Вместе мы сделаем VET UNION Assistant лучше! ⚡️"
#     )

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
    waiting_for_employee_last_name = State()  
    waiting_for_employee_first_name = State()  
    waiting_for_department = State()

@registration_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} initiated registration")
    
    # Проверяем, есть ли параметры (deep link)
    args = message.text.strip().split(maxsplit=1)
    
    if len(args) > 1:
        param = args[1]
        
        # Поддерживаем разные форматы deep link
        test_code = None
        
        if param.startswith("test_"):
            # Новый формат с base64
            encoded_code = param[5:]
            test_code = decode_test_code_from_url(encoded_code)
            print(f"[DEBUG] Deep link: encoded='{encoded_code}' -> decoded='{test_code}'")
            
        elif param.startswith("t_"):
            # Альтернативный короткий формат (если будете использовать)
            short_code = param[2:]
            test_code = await db.get_test_by_short_code(short_code)  # Если храните в БД
            
        else:
            # Возможно, это прямой код теста (для обратной совместимости)
            test_code = param
            print(f"[DEBUG] Direct test code in deep link: {test_code}")
        
        if test_code:
            # Проверяем, зарегистрирован ли пользователь
            user_exists = await db.user_exists(user_id)
            
            if not user_exists:
                # Сохраняем для обработки после регистрации
                await state.update_data(pending_test_code=test_code)
                await message.answer(
                    "Для просмотра информации о тестах необходимо пройти регистрацию.\n\n"
                    f"После регистрации вы автоматически получите информацию о тесте <b>{test_code}</b>.\n\n"
                    "Выберите, кто вы:",
                    reply_markup=get_user_type_kb(),
                    parse_mode="HTML"
                )
                await state.set_state(RegistrationStates.waiting_for_user_type)
                return
            
            # Пользователь зарегистрирован - показываем тест
            await process_test_request(message, state, test_code, user_id)
            return
    
    # Обычная логика /start без deep link
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
        
async def process_test_request(message: Message, state: FSMContext, test_code: str, user_id: int):
    """Обрабатывает запрос теста через deep link."""
    
    loading_msg = await message.answer(f"🔍 Загружаю информацию о тесте <b>{test_code}</b>...", parse_mode="HTML")
    
    try:
        processor = DataProcessor()
        processor.load_vector_store()
        
        # Используем smart_test_search для максимальной надежности
        result, found_variant, match_type = await smart_test_search(processor, test_code)
        
        if result:
            doc = result[0]
            test_data = format_test_data(doc.metadata)
            
            # Удаляем сообщение о загрузке
            try:
                await loading_msg.delete()
            except:
                pass
            
            # Формируем ответ
            response = format_test_info(test_data)
            
            # Отправляем с фото
            await send_test_info_with_photo(message, test_data, response)
            
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
            
            # ============================================
            # FIX: Используем get_dialog_kb() для режима диалога
            # ============================================
            await state.set_state(QuestionStates.waiting_for_search_type)  # Устанавливаем состояние диалога
            await message.answer(
                "Готов к новому запросу! Введите код теста или опишите, что ищете:",
                reply_markup=get_dialog_kb()  # ← ИЗМЕНЕНО с get_main_menu_kb()
            )
            
            print(f"[INFO] Successfully processed deep link for test {test_code}")
            
        else:
            # Тест не найден
            try:
                await loading_msg.delete()
            except:
                pass
            
            # Записываем неудачную попытку
            await db.add_search_history(
                user_id=user_id,
                search_query=f"Deep link: {test_code}",
                search_type='code',
                success=False
            )
            
            await message.answer(
                f"❌ Тест <b>{test_code}</b> не найден в базе данных.\n\n"
                "Возможно, код теста был изменен или удален.\n"
                "Попробуйте воспользоваться поиском.",
                parse_mode="HTML"
            )
            
            # Показываем главное меню
            user = await db.get_user(user_id)
            menu_kb = get_admin_menu_kb() if user['role'] == 'admin' else get_main_menu_kb()
            await message.answer("Выберите действие:", reply_markup=menu_kb)
            
            print(f"[WARNING] Test {test_code} not found via deep link")
            
    except Exception as e:
        print(f"[ERROR] Deep link processing failed for {test_code}: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            await loading_msg.delete()
        except:
            pass
        
        await message.answer(
            "⚠️ Произошла ошибка при загрузке информации о тесте.\n"
            "Попробуйте позже или воспользуйтесь поиском.",
            parse_mode="HTML"
        )
        
        # Показываем главное меню
        user = await db.get_user(user_id)
        menu_kb = get_admin_menu_kb() if user['role'] == 'admin' else get_main_menu_kb()
        await message.answer("Выберите действие:", reply_markup=menu_kb)

@registration_router.message(RegistrationStates.waiting_for_user_type)
async def process_user_type(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text == "👨‍⚕️ Ветеринарный врач клиники-партнера":
        await state.update_data(user_type='client')
    elif message.text == "🔬 Сотрудник X-LAB VET":
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
            "💡 Код клиники вы можете получить у представителя X-LAB VET",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(RegistrationStates.waiting_for_client_code)
    else:
        # Для сотрудников показываем регионы выбранной страны
        await message.answer(
            "📝 Регистрация сотрудника X-LAB VET\n\n"
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
    name = message.text.strip().title()  # Добавлен .title()

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
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 Имя: {data['name']}\n"
            f"🏥 Код клиники: {data['client_code']}\n"
            f"📋 Специализация: {specialization}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
        await message.answer(await get_tech_support_message())
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
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 Имя: {data['name']}\n"
            f"🏥 Код клиники: {data['client_code']}\n"
            f"📋 Специализация: {specialization}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
        await message.answer(await get_tech_support_message())
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
    
    data = await state.get_data()
    
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
        "Введите вашу фамилию:",  # Сначала запрашиваем фамилию
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_employee_last_name)
    
@registration_router.message(RegistrationStates.waiting_for_employee_last_name)
async def process_employee_last_name(message: Message, state: FSMContext):
    last_name = message.text.strip().title()  # Добавлен .title()

    if len(last_name) < 2 or len(last_name) > 50:
        await message.answer(
            "❌ Фамилия должна содержать от 2 до 50 символов.\nПопробуйте еще раз:"
        )
        return
    
    # Проверяем, что введены только буквы и дефис
    if not all(c.isalpha() or c in ['-', ' '] for c in last_name):
        await message.answer(
            "❌ Фамилия может содержать только буквы, пробел и дефис.\nПопробуйте еще раз:"
        )
        return

    await state.update_data(last_name=last_name)
    await message.answer(
        f"👤 Фамилия: {last_name}\n\n"
        "Теперь введите ваше имя:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_employee_first_name)

@registration_router.message(RegistrationStates.waiting_for_employee_first_name)
async def process_employee_first_name(message: Message, state: FSMContext):
    first_name = message.text.strip().title()  # Добавлен .title()

    if len(first_name) < 2 or len(first_name) > 50:
        await message.answer(
            "❌ Имя должно содержать от 2 до 50 символов.\nПопробуйте еще раз:"
        )
        return
    
    # Проверяем, что введены только буквы и дефис
    if not all(c.isalpha() or c in ['-', ' '] for c in first_name):
        await message.answer(
            "❌ Имя может содержать только буквы, пробел и дефис.\nПопробуйте еще раз:"
        )
        return

    data = await state.get_data()
    await state.update_data(first_name=first_name)
    
    await message.answer(
        f"👤 {data['last_name']} {first_name}\n\n"
        "Выберите функцию, которую вы исполняете:",
        reply_markup=get_department_function_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_department)

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
        "Введите вашу фамилию:",  # Сначала запрашиваем фамилию
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_employee_last_name)

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
    
    # Используем новую версию функции с раздельными именем и фамилией
    success = await db.add_employee(
        telegram_id=user_id,
        first_name=data['first_name'],
        last_name=data['last_name'],
        region=data['region'],
        department_function=department_map[message.text],
        country=data['country']
    )

    if success:
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 {data['last_name']} {data['first_name']}\n"
            f"📍 Регион: {data['region']}\n"
            f"🏢 Функция: {message.text}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
        await message.answer(await get_tech_support_message())
        # Проверяем наличие отложенного теста
        if 'pending_test_code' in data:
            test_code = data['pending_test_code']
            await state.clear()
            await process_test_request(message, state, test_code, user_id)
        else:
            await state.clear()
    else:
        await message.answer(
            "❌ Ошибка регистрации. Попробуйте еще раз: /start",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()

async def finish_registration(message: Message, state: FSMContext, user_type: str):
    """Завершает регистрацию и обрабатывает отложенный тест если есть."""
    
    data = await state.get_data()
    
    # Проверяем наличие отложенного теста
    if 'pending_test_code' in data:
        test_code = data['pending_test_code']
        print(f"[INFO] Processing pending test {test_code} after registration")
        
        # Очищаем состояние перед обработкой теста
        await state.clear()
        
        # Обрабатываем тест
        await process_test_request(message, state, test_code, message.from_user.id)
    else:
        # Просто очищаем состояние
        await state.clear()

    await state.clear()
