import os
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.types import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from bot.handlers import start_router, analysis_router

from dotenv import load_dotenv
ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

BOT_API_KEY = os.getenv("BOT_API_KEY")
if not BOT_API_KEY:
    raise RuntimeError(f"BOT_API_KEY not found in {ENV_PATH}")


bot = Bot(
    token=BOT_API_KEY, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
dp.include_router(start_router)
dp.include_router(analysis_router)
