import random
import string
from aiogram import Router, F
from aiogram.types import Message
from bot.keyboards import get_cancel_kb, get_admin_menu_kb

from src.database.db_init import db

admin_router = Router()

@admin_router.message(F.text == "🔐 Создать код")
async def create_code(message: Message):
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} requested code creation")
    
    user = await db.get_user(user_id)
    
    if not user or user['role'] != 'admin':
        print(f"[WARN] User {user_id} has no access to create codes")
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    # Генерируем случайный код
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    staff_code = f"STAFF{code}"
    admin_code = f"ADMIN{code}"
    
    print(f"[INFO] Generated staff code: {staff_code}")
    print(f"[INFO] Generated admin code: {admin_code}")
    
    await db.create_activation_code(staff_code, "staff")
    await db.create_activation_code(admin_code, "admin")
    
    print(f"[INFO] Activation codes saved to database for user {user_id}")
    
    await message.answer(
        "✅ Коды активации созданы:\n\n"
        f"👷 Для сотрудника: `{staff_code}`\n"
        f"👨‍💼 Для администратора: `{admin_code}`\n\n"
        "Коды одноразовые и действуют бессрочно.",
        parse_mode="Markdown",
        reply_markup=get_admin_menu_kb()
    )
    print(f"[INFO] Activation codes sent to user {user_id}")

@admin_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} requested system statistics")
    
    user = await db.get_user(user_id)
    
    if not user or user['role'] != 'admin':
        print(f"[WARN] User {user_id} has no access to view statistics")
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    stats = await db.get_statistics()
    
    print(f"[INFO] Statistics retrieved for user {user_id}")
    
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
    print(f"[INFO] Statistics sent to user {user_id}")
