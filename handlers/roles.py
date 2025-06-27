from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from database.models import Database
from keyboards.reply import get_main_menu_kb, get_staff_menu_kb
from config import DATABASE_PATH

router = Router()
db = Database(DATABASE_PATH)

@router.message(Command("activate"))
async def activate_role(message: Message):
    # Проверяем формат команды
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "Неверный формат команды.\n"
            "Используйте: /activate КОД"
        )
        return
    
    code = parts[1]
    
    # Проверяем код
    activation = await db.check_activation_code(code)
    if not activation:
        await message.answer("❌ Неверный или истекший код активации")
        return
    
    # Активируем роль
    await db.update_user_role(message.from_user.id, activation['role'])
    await db.use_activation_code(code)
    
    # Определяем клавиатуру в зависимости от роли
    keyboard = get_staff_menu_kb() if activation['role'] == 'staff' else get_main_menu_kb()
    
    await message.answer(
        f"✅ Роль '{activation['role']}' успешно активирована!\n"
        f"Теперь вам доступны расширенные возможности.",
        reply_markup=keyboard
    )