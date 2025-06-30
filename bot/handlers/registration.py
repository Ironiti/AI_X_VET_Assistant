import re
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_kb, get_country_kb, get_pet_type_kb, get_main_menu_kb

from src.database.db_init import db

registration_router = Router()

class RegistrationStates(StatesGroup):
    waiting_for_country = State()
    waiting_for_name = State()
    waiting_for_client_code = State()
    waiting_for_pet_name = State()
    waiting_for_pet_type = State()

@registration_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} initiated registration")

    await state.clear()
    user_exists = await db.user_exists(user_id)

    if user_exists:
        print(f"[INFO] User {user_id} already registered")
        await message.answer(
            "Вы уже зарегистрированы! 🎉\n"
            "Используйте меню для дальнейшей работы.",
            reply_markup=get_main_menu_kb()
        )
    else:
        print(f"[INFO] User {user_id} starting new registration")
        await message.answer(
            "Добро пожаловать в бот ветеринарной клиники! 🏥\n"
            "Давайте пройдем регистрацию.\n\n"
            "Выберите вашу страну:",
            reply_markup=get_country_kb()
        )
        await state.set_state(RegistrationStates.waiting_for_country)
        print(f"[INFO] State set to waiting_for_country for user {user_id}")

@registration_router.message(StateFilter(RegistrationStates), F.text == "❌ Отмена")
async def cancel_registration(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    await message.answer(
        "Регистрация отменена. Для начала регистрации используйте /start",
        reply_markup=ReplyKeyboardRemove()
    )
    print(f"[INFO] User {user_id} cancelled registration")

@registration_router.message(RegistrationStates.waiting_for_country)
async def process_country(message: Message, state: FSMContext):
    user_id = message.from_user.id
    country_map = {
        "🇷🇺 Россия": "RU",
        "🇧🇾 Беларусь": "BY",
        "🇰🇿 Казахстан": "KZ"
    }

    if message.text not in country_map:
        print(f"[WARN] User {user_id} selected invalid country: {message.text}")
        await message.answer(
            "❌ Пожалуйста, выберите страну из предложенных вариантов",
            reply_markup=get_country_kb()
        )
        return

    await state.update_data(country=country_map[message.text], country_name=message.text)
    print(f"[INFO] User {user_id} selected country: {country_map[message.text]}")
    await message.answer(
        "Введите ваше имя:\n⚠️ Используйте только буквы и пробелы (2-50 символов)",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_name)
    print(f"[INFO] State set to waiting_for_name for user {user_id}")

@registration_router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()

    if len(name) < 2 or len(name) > 50 or not re.match(r'^[а-яА-ЯёЁa-zA-Z\s]+$', name):
        print(f"[WARN] User {user_id} entered invalid name: {name}")
        await message.answer(
            "❌ Имя должно содержать только буквы и пробелы (2-50 символов).\nПопробуйте еще раз:"
        )
        return

    await state.update_data(username=name)
    print(f"[INFO] User {user_id} saved name: {name}")
    await message.answer(
        "Отлично! Теперь введите ваш код клиента:\n"
        "⚠️ Код должен начинаться с 'В+' (например: В+МАКСИМА)\n"
        "(Код клиента вы можете получить в нашей клинике)"
    )
    await state.set_state(RegistrationStates.waiting_for_client_code)
    print(f"[INFO] State set to waiting_for_client_code for user {user_id}")

@registration_router.message(RegistrationStates.waiting_for_client_code)
async def process_client_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip().upper()

    if len(code) < 3 or len(code) > 11 or not re.match(r'^[ВC]\+[А-ЯA-Z0-9\-]+$', code):
        print(f"[WARN] User {user_id} entered invalid client code: {code}")
        await message.answer(
            "❌ Неверный формат кода клиента.\nКод должен начинаться с 'В+' и содержать только заглавные буквы и цифры.\n"
            "Например: В+МАКСИМА\nПопробуйте еще раз:"
        )
        return

    existing = await db.check_client_code_exists(code)
    if existing:
        print(f"[WARN] User {user_id} tried to use existing client code: {code}")
        await message.answer(
            "❌ Этот код клиента уже зарегистрирован.\nПопробуйте еще раз:"
        )
        return

    await state.update_data(client_code=code)
    print(f"[INFO] User {user_id} saved client code: {code}")
    await message.answer(
        "Введите кличку вашего питомца:\n⚠️ От 2 до 30 символов"
    )
    await state.set_state(RegistrationStates.waiting_for_pet_name)
    print(f"[INFO] State set to waiting_for_pet_name for user {user_id}")

@registration_router.message(RegistrationStates.waiting_for_pet_name)
async def process_pet_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pet_name = message.text.strip()

    if len(pet_name) < 2 or len(pet_name) > 30 or not re.match(r'^[а-яА-ЯёЁa-zA-Z0-9\s\-]+$', pet_name):
        print(f"[WARN] User {user_id} entered invalid pet name: {pet_name}")
        await message.answer(
            "❌ Кличка может содержать только буквы, цифры, пробелы и дефис (2-30 символов).\nПопробуйте еще раз:"
        )
        return

    await state.update_data(pet_name=pet_name)
    print(f"[INFO] User {user_id} saved pet name: {pet_name}")
    await message.answer(
        "Выберите тип вашего питомца:",
        reply_markup=get_pet_type_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_pet_type)
    print(f"[INFO] State set to waiting_for_pet_type for user {user_id}")

@registration_router.message(RegistrationStates.waiting_for_pet_type)
async def process_pet_type(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pet_types = ["🐕 Собака", "🐈 Кошка", "🐰 Кролик", "🦜 Птица", "🐹 Грызун", "🦎 Рептилия", "Другое"]

    if message.text not in pet_types:
        print(f"[WARN] User {user_id} selected invalid pet type: {message.text}")
        await message.answer(
            "❌ Пожалуйста, выберите тип питомца из предложенных вариантов",
            reply_markup=get_pet_type_kb()
        )
        return

    data = await state.get_data()
    user = message.from_user

    success = await db.add_user(
        telegram_id=user.id,
        username=data['username'],
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        language_code=user.language_code or "",
        is_bot=user.is_bot,
        chat_type=message.chat.type,
        client_code=data['client_code'],
        pet_name=data['pet_name'],
        pet_type=message.text
    )

    if success:
        print(f"[INFO] User {user_id} registered successfully")
        await message.answer(
            f"✅ Регистрация завершена успешно!\n\n"
            f"👤 Имя: {data['username']}\n"
            f"🆔 Код клиента: {data['client_code']}\n"
            f"🐾 Питомец: {data['pet_name']}\n"
            f"📝 Тип: {message.text}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
        await db.add_request_stat(
            user_id,
            "registration",
            f"User registered with code {data['client_code']}"
        )
    else:
        print(f"[ERROR] Registration failed for user {user_id}")
        await message.answer(
            "❌ Ошибка регистрации. Попробуйте еще раз: /start",
            reply_markup=ReplyKeyboardRemove()
        )

    await state.clear()
    print(f"[INFO] State cleared for user {user_id}")
