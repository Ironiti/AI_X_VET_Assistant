from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import or_f, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_kb, get_menu_by_role

from src.database.db_init import db

activation_router = Router()

class ActivationStates(StatesGroup):
    waiting_for_code = State()

@activation_router.message(or_f(
    F.text == "🔑 Активировать код",
    Command("activate")
))
async def start_activation(message: Message, state: FSMContext):
    print(f"[INFO] Activation requested by user {message.from_user.id}")
    
    user = await db.get_user(message.from_user.id)
    
    if not user:
        print(f"[WARN] User {message.from_user.id} not registered, prompting /start")
        await message.answer(
            "Сначала необходимо пройти регистрацию.\n"
            "Используйте команду /start"
        )
        return
    
    current_role = user['role']
    if current_role != 'client':
        role_names = {
            'admin': 'Администратор',
            'staff': 'Сотрудник'
        }
        role_name = role_names.get(current_role, current_role)
        print(f"[INFO] User {message.from_user.id} already has role: {role_name}")
        await message.answer(
            f"У вас уже активирована роль: {role_name}\n"
            "Повторная активация не требуется.",
            reply_markup=get_menu_by_role(current_role)
        )
        return
    
    print(f"[INFO] User {message.from_user.id} prompted to enter activation code")
    await message.answer(
        "🔑 Введите код активации:\n\n"
        "Коды выдаются администрацией клиники для сотрудников.",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(ActivationStates.waiting_for_code)

@activation_router.message(ActivationStates.waiting_for_code)
async def process_activation_code(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        print(f"[INFO] User {message.from_user.id} cancelled activation")
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role('client'))
        return
    
    code = message.text.strip().upper()
    print(f"[INFO] User {message.from_user.id} entered activation code: {code}")
    
    activation = await db.check_activation_code(code)
    
    if not activation:
        print(f"[WARN] Invalid or used activation code by user {message.from_user.id}: {code}")
        await message.answer(
            "❌ Неверный или уже использованный код активации.\n"
            "Проверьте правильность ввода.",
            reply_markup=get_menu_by_role('client')
        )
        await state.clear()
        return
    
    await db.use_activation_code(code, message.from_user.id)
    new_role = activation['role']
    await db.update_user_role(message.from_user.id, new_role)
    
    role_names = {
        'admin': 'Администратор',
        'staff': 'Сотрудник'
    }
    role_name = role_names.get(new_role, new_role)
    
    print(f"[INFO] User {message.from_user.id} activated new role: {new_role}")
    
    await message.answer(
        f"✅ Код успешно активирован!\n"
        f"🎭 Ваша роль: {role_name}\n\n"
        f"Теперь вам доступны расширенные возможности.",
        reply_markup=get_menu_by_role(new_role)
    )
    
    await db.add_request_stat(
        message.from_user.id,
        "code_activation",
        f"Активирована роль: {new_role}"
    )
    
    print(f"[INFO] Activation stat logged for user {message.from_user.id}")
    await state.clear()
