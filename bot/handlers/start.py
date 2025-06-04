from aiogram import Router, Message
from aiogram.filters.command import CommandStart

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("Заглушка")
