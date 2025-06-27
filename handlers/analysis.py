from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

# Вариант 1: Для обработки команды /analyze
@router.message(Command("analyze"))
async def analyze_handler(message: Message):
    await message.answer("Анализ данных...")

# Вариант 2: Если нужно обрабатывать все сообщения
@router.message()
async def any_message_handler(message: Message):
    await message.answer("Получено сообщение")

__all__ = ["router"]