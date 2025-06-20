from aiogram import Router, F, html
from aiogram.types import Message
from aiogram.filters.command import CommandStart, Command
from aiogram.utils.markdown import hbold

from src.database.db_init import add_user, get_user

default_router = Router()

@default_router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    add_user(user.id, user.username, user.full_name)
    
    db_user = get_user(user.id)
    
    await message.answer(
        f"Привет, {hbold(user.full_name)}!\n"
        f"Ты зарегистрирован с {db_user[3]}"
    )


@default_router.message(Command('help'))
async def cmd_start(message: Message):
    await message.answer("Обратитесь за помощью к @Michael_BY_23")
