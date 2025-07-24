from aiogram import Router, F
from aiogram.types import Message

gif_router = Router()

@gif_router.message(F.animation)
async def get_gif_id(message: Message):
    await message.answer(f"GIF ID: {message.animation.file_id}")
    