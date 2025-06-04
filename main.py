from aiogram import Dispatcher
from bot import bot, dp

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())