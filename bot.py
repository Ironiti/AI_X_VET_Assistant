import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, DATABASE_PATH
from database.models import Database
from handlers import registration, feedback, activation, questions, admin

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

async def on_startup():
    # Создание таблиц в БД
    db = Database(DATABASE_PATH)
    await db.create_tables()
    logging.info("База данных инициализирована")

async def main():
    # Регистрация роутеров
    dp.include_router(registration.router)
    dp.include_router(feedback.router)  # Переименовали из callback
    dp.include_router(activation.router)
    dp.include_router(questions.router)
    dp.include_router(admin.router)
    
    # Запуск бота
    await on_startup()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())