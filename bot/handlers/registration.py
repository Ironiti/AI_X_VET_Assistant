from aiogram import Router, html
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.database.db_init import Database
from bot.keyboards import get_cancel_kb, get_pet_type_kb, get_main_menu_kb
from config import DATABASE_PATH

registration_router = Router()
db = Database(DATABASE_PATH)

class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_client_code = State()
    waiting_for_pet_name = State()
    waiting_for_pet_type = State()

@registration_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    # Ensure DB schema is ready
    await db.create_tables()

    # Add or ignore basic user metadata
    await db.add_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name or "",
        language_code=user.language_code or "",
        is_bot=user.is_bot,
        chat_type=message.chat.type
    )

    # Check if fully registered (clinic user)
    exists = await db.user_exists(user.id)
    # Assuming client_code marks full registration
    user_data = await db.get_user(user.id)
    if exists and user_data['client_code']:
        await message.answer(
            f"Привет, {html.hbold(user.full_name)}! 🎉\n"
            f"Вы уже зарегистрированы. Ваш код клиента: {user_data['client_code']}",
            reply_markup=get_main_menu_kb()
        )
        return

    # Begin full registration
    await message.answer(
        "Добро пожаловать в бот ветеринарной клиники! 🏥\n"
        "Давайте пройдем регистрацию.\n\n"
        "Введите ваше имя:",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_name)
    print(f"[INFO] Registration started for user {user.id}")

@registration_router.message(lambda message: message.text == "❌ Отмена")
async def cancel_registration(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Регистрация отменена. Для начала регистрации используйте /start",
        reply_markup=None
    )
    print(f"[INFO] Registration canceled for user {message.from_user.id}")

@registration_router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer(
        "Отлично! Теперь введите ваш код клиента:\n"
        "(Код клиента вы можете получить в нашей клинике)"
    )
    await state.set_state(RegistrationStates.waiting_for_client_code)
    print(f"[INFO] Collected name for user {message.from_user.id}: {message.text}")

@registration_router.message(RegistrationStates.waiting_for_client_code)
async def process_client_code(message: Message, state: FSMContext):
    await state.update_data(client_code=message.text)
    await message.answer("Введите кличку вашего питомца:")
    await state.set_state(RegistrationStates.waiting_for_pet_name)
    print(f"[INFO] Collected client_code for user {message.from_user.id}: {message.text}")

@registration_router.message(RegistrationStates.waiting_for_pet_name)
async def process_pet_name(message: Message, state: FSMContext):
    await state.update_data(pet_name=message.text)
    await message.answer(
        "Выберите тип вашего питомца:",
        reply_markup=get_pet_type_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_pet_type)
    print(f"[INFO] Collected pet_name for user {message.from_user.id}: {message.text}")

@registration_router.message(RegistrationStates.waiting_for_pet_type)
async def process_pet_type(message: Message, state: FSMContext):
    pet_types = ["🐕 Собака", "🐈 Кошка", "🐰 Кролик", "🦜 Птица", "🐹 Грызун", "🦎 Рептилия", "Другое"]
    if message.text not in pet_types:
        await message.answer("Пожалуйста, выберите тип питомца из предложенных вариантов")
        return

    data = await state.get_data()
    success = await db.add_user(
        telegram_id=message.from_user.id,
        username=data['username'],
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name or "",
        language_code=message.from_user.language_code or "",
        is_bot=message.from_user.is_bot,
        chat_type=message.chat.type,
        client_code=data['client_code'],
        pet_name=data['pet_name'],
        pet_type=message.text
    )

    if success:
        await message.answer(
            f"Регистрация завершена успешно! ✅\n\n"
            f"👤 Имя: {data['username']}\n"
            f"🆔 Код клиента: {data['client_code']}\n"
            f"🐾 Питомец: {data['pet_name']}\n"
            f"📝 Тип: {message.text}\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            reply_markup=get_main_menu_kb()
        )
        await db.add_request_stat(
            message.from_user.id,
            "registration",
            "Пользователь успешно зарегистрирован"
        )
        print(f"[INFO] User {message.from_user.id} fully registered")
    else:
        await message.answer(
            "Ошибка регистрации. Возможно, данный код клиента уже используется.\n"
            "Попробуйте еще раз: /start",
            reply_markup=None
        )
        print(f"[ERROR] Registration failed for user {message.from_user.id}")

    await state.clear()
