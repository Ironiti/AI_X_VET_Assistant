from aiogram import Bot, Dispatcher
from aiogram.types import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.default import default_router
from bot.handlers.get_phone import get_phone_router
from bot.handlers.registration import registration_router
from config import BOT_API_KEY

if not BOT_API_KEY:
    raise RuntimeError('BOT_API_KEY not found.')

bot = Bot(
    token=BOT_API_KEY, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(default_router)
dp.include_router(get_phone_router)
dp.include_router(registration_router)
