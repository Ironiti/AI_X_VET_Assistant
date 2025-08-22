from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.poll_sender import poll_callback_router
from bot.handlers.registration import registration_router
from bot.handlers.feedback import feedback_router
from bot.handlers.activation import activation_router
from bot.handlers.questions import questions_router
from bot.handlers.admin import admin_router
from bot.handlers.help import help_router
from bot.handlers.utils import gif_router
# from .questions import questions_router, questions_callbacks_router
from config import BOT_API_KEY

if not BOT_API_KEY:
    raise RuntimeError('BOT_API_KEY not found.')

bot = Bot(
    token=BOT_API_KEY, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(registration_router)
# dp.include_router(questions_callbacks_router)
dp.include_router(feedback_router)
dp.include_router(poll_callback_router)
dp.include_router(activation_router)
dp.include_router(questions_router)
dp.include_router(admin_router)
dp.include_router(help_router)
dp.include_router(gif_router)
