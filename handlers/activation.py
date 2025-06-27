from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Database
from keyboards.reply import get_cancel_kb, get_menu_by_role
from config import DATABASE_PATH
import logging

router = Router()
db = Database(DATABASE_PATH)
logger = logging.getLogger(__name__)

class ActivationStates(StatesGroup):
    waiting_for_code = State()

@router.message(F.text == "🔑 Активировать код")
@router.message(Command("activate"))
async def start_activation(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    
    if not user:
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
        await message.answer(
            f"У вас уже активирована роль: {role_names.get(current_role, current_role)}\n"
            "Повторная активация не требуется.",
            reply_markup=get_menu_by_role(current_role)
        )
        return
    
    await message.answer(
        "🔑 Введите код активации:\n\n"
        "Коды выдаются администрацией клиники для сотрудников.",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(ActivationStates.waiting_for_code)

@router.message(ActivationStates.waiting_for_code)
async def process_activation_code(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role('client'))
        return
    
    code = message.text.strip().upper()
    
    # Проверяем код активации
    activation = await db.check_activation_code(code)
    
    if not activation:
        await message.answer(
            "❌ Неверный или уже использованный код активации.\n"
            "Проверьте правильность ввода.",
            reply_markup=get_menu_by_role('client')
        )
        await state.clear()
        return
    
    # Используем код
    await db.use_activation_code(code, message.from_user.id)
    
    # Обновляем роль пользователя
    new_role = activation['role']
    await db.update_user_role(message.from_user.id, new_role)
    
    role_names = {
        'admin': 'Администратор',
        'staff': 'Сотрудник'
    }
    
    role_name = role_names.get(new_role, new_role)
    
    await message.answer(
        f"✅ Код успешно активирован!\n"
        f"🎭 Ваша роль: {role_name}\n\n"
        f"Теперь вам доступны расширенные возможности.",
        reply_markup=get_menu_by_role(new_role)
    )
    
    # Логируем активацию
    await db.add_request_stat(
        message.from_user.id,
        "code_activation",
        f"Активирована роль: {new_role}"
    )
    
    logger.info(f"User {message.from_user.id} activated role: {new_role}")
    await state.clear()