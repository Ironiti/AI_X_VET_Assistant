from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_kb, get_admin_menu_kb, get_main_menu_kb, get_back_to_menu_kb

from src.database.db_init import db

activation_router = Router()

class ActivationStates(StatesGroup):
    waiting_for_code = State()

@activation_router.message(F.text == "🔑 Активировать код")
async def start_activation(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Необходимо пройти регистрацию. Используйте /start")
        return
    
    if user['role'] == 'admin':
        await message.answer(
            "Вы уже являетесь администратором!",
            reply_markup=get_admin_menu_kb()
        )
        return
    
    await message.answer(
        "Введите код активации администратора:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(ActivationStates.waiting_for_code)

@activation_router.message(ActivationStates.waiting_for_code)
async def process_activation_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_main_menu_kb())
        return
    
    code = message.text.strip().upper()
    activation = await db.check_activation_code(code)
    
    if activation:
        await db.use_activation_code(code, user_id)
        await db.update_user_role(user_id, 'admin')
        
        await message.answer(
            "✅ Код успешно активирован!\n"
            "Теперь вы администратор системы.",
            reply_markup=get_admin_menu_kb()
        )
    else:
        await message.answer(
            "❌ Неверный или уже использованный код.\n"
            "Попробуйте еще раз или нажмите Отмена.",
            reply_markup=get_back_to_menu_kb()
        )
        return
    
    await state.clear()