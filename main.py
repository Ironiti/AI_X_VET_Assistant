import asyncio
from bot import bot, dp
from src.database.models import Database
from config import DATABASE_PATH

async def main():
    db = Database(DATABASE_PATH)
    await db.create_tables()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Shut down')