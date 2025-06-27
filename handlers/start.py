from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart

from bot.db_utils import add_user, get_user

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    # Добавляем пользователя в БД
    user = message.from_user
    add_user(user.id, user.username, user.full_name)
    
    # Получаем информацию о пользователе
    db_user = get_user(user.id)
    
    await message.answer(
        f"Привет, {user.full_name}!\n"
        f"Ты зарегистрирован с {db_user[3]}"
    )