import re
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import (
    get_cancel_kb, get_user_type_kb, get_department_function_kb, 
    get_main_menu_kb, get_admin_menu_kb, get_specialization_kb,
    get_region_kb
)

from src.database.db_init import db

registration_router = Router()

class RegistrationStates(StatesGroup):
    waiting_for_user_type = State()
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

@registration_router.message(StateFilter(RegistrationStates), F.text == "❌ Отмена")
async def cancel_registration(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    await message.answer(
        "Регистрация отменена. Для начала регистрации используйте /start",
        reply_markup=ReplyKeyboardRemove()
    )
    print(f"[INFO] User {user_id} cancelled registration")

@registration_router.message(RegistrationStates.waiting_for_user_type)
async def process_user_type(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text == "👨‍⚕️ Ветеринарный врач клиники-партнера":
        await state.update_data(user_type='client')
        await message.answer(
            "📝 Регистрация ветеринарного врача\n\n"
            "Введите ваш код клиники:\n"
            "⚠️ Код должен начинаться с 'В+' (например: В+МАКСИМА)\n"
            "💡 Код клиники вы можете получить у представителя VET UNION",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(RegistrationStates.waiting_for_client_code)
        
    elif message.text == "👷 Сотрудник VET UNION":
        await state.update_data(user_type='employee')
        await message.answer(
            "📝 Регистрация сотрудника VET UNION\n\n"
            "Выберите ваш регион:",
            reply_markup=get_region_kb()
        )
        await state.set_state(RegistrationStates.waiting_for_region)
        
    else:
        await message.answer(
            "❌ Пожалуйста, выберите из предложенных вариантов",
            reply_markup=get_user_type_kb()
        )

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
            "• Пример: В+МАКСИМА\n\n"
            "Попробуйте еще раз:"
        )
        return

    await state.update_data(client_code=code)
    await message.answer(
        f"✅ Код клиники: {code}\n\n"
        "Теперь введите ваше имя:",
        reply_markup=get_cancel_kb()
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
            reply_markup=get_cancel_kb()
        )
        await state.set_state(RegistrationStates.waiting_for_custom_specialization)
        return
    
    specialization_map = {
        "🏥 Общая практика": "Общая практика",
        "💊 Терапевт": "Терапевт",
        "🔪 Хирург": "Хирург",
        "🔬 Лаборант": "Лаборант",
        "🦷 Стоматолог": "Стоматолог",
        "👁 Офтальмолог": "Офтальмолог",
        "🧠 Невролог": "Невролог",
        "🦴 Ортопед": "Ортопед",
        "❤️ Кардиолог": "Кардиолог"
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
        specialization=specialization
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
    else:
        await message.answer(
            "❌ Ошибка регистрации. Попробуйте еще раз: /start",
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
        specialization=specialization
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
    else:
        await message.answer(
            "❌ Ошибка регистрации. Попробуйте еще раз: /start",
            reply_markup=ReplyKeyboardRemove()
        )

    await state.clear()

# Обработчики для сотрудников
@registration_router.message(RegistrationStates.waiting_for_region)
async def process_region(message: Message, state: FSMContext):
    if message.text == "✏️ Ввести свой регион":
        await message.answer(
            "Введите ваш регион:",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(RegistrationStates.waiting_for_custom_region)
        return
    
    region_map = {
        "📍 Минск": "Минск",
        "📍 Минская область": "Минская область",
        "📍 Брест": "Брест",
        "📍 Брестская область": "Брестская область",
        "📍 Витебск": "Витебск",
        "📍 Витебская область": "Витебская область",
        "📍 Гомель": "Гомель",
        "📍 Гомельская область": "Гомельская область",
        "📍 Гродно": "Гродно",
        "📍 Гродненская область": "Гродненская область",
        "📍 Могилёв": "Могилёв",
        "📍 Могилёвская область": "Могилёвская область"
    }
    
    if message.text not in region_map:
        await message.answer(
            "❌ Пожалуйста, выберите регион из списка или введите свой",
            reply_markup=get_region_kb()
        )
        return
    
    region = region_map[message.text]
    await state.update_data(region=region)
    await message.answer(
        f"📍 Регион: {region}\n\n"
        "Введите вашу фамилию и имя:",
        reply_markup=get_cancel_kb()
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
        reply_markup=get_cancel_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_employee_name)

@registration_router.message(RegistrationStates.waiting_for_employee_name)
async def process_employee_name(message: Message, state: FSMContext):
    name = message.text.strip()

    if len(name) < 3 or len(name) > 100:
        await message.answer(
            "❌ ФИО должно содержать от 3 до 100 символов.\nПопробуйте еще раз:"
        )
        return

    await state.update_data(name=name)
    await message.answer(
        f"👤 ФИО: {name}\n\n"
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
        department_function=department_map[message.text]
    )

    if success:
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 ФИО: {data['name']}\n"
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