from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Database
from keyboards.reply import get_cancel_kb, get_admin_menu_kb
from config import DATABASE_PATH
import random
import string

router = Router()
db = Database(DATABASE_PATH)

class CreateCodeStates(StatesGroup):
    waiting_for_role = State()

@router.message(F.text == "🔐 Создать код")
async def create_code(message: Message):
    user = await db.get_user(message.from_user.id)
    
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    # Генерируем случайный код
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    # Создаем коды для обеих ролей
    staff_code = f"STAFF{code}"
    admin_code = f"ADMIN{code}"
    
    await db.create_activation_code(staff_code, "staff")
    await db.create_activation_code(admin_code, "admin")
    
    await message.answer(
        "✅ Коды активации созданы:\n\n"
        f"👷 Для сотрудника: `{staff_code}`\n"
        f"👨‍💼 Для администратора: `{admin_code}`\n\n"
        "Коды одноразовые и действуют бессрочно.",
        parse_mode="Markdown",
        reply_markup=get_admin_menu_kb()
    )

@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    user = await db.get_user(message.from_user.id)
    
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    # Получаем статистику
    stats = await db.get_statistics()
    
    await message.answer(
        f"📊 Статистика системы:\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"├ Клиентов: {stats['clients']}\n"
        f"├ Сотрудников: {stats['staff']}\n"
        f"└ Администраторов: {stats['admins']}\n\n"
        f"📋 Обращений: {stats['total_requests']}\n"
        f"❓ Вопросов: {stats['questions']}\n"
        f"📞 Звонков: {stats['callbacks']}\n"
        f"💡 Предложений: {stats['suggestions']}\n"
        f"⚠️ Жалоб: {stats['complaints']}",
        reply_markup=get_admin_menu_kb()
    )