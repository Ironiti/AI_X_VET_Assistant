import asyncio
from bot.handlers import bot, dp
from src.database.db_init import db

async def main():
    await db.create_tables()
    print("[INFO] Starting bot polling…")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Shut down')
