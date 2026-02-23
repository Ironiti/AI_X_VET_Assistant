"""
Простой скрипт для получения file_id из Telegram
Использование:
1. Вставьте свой токен бота ниже
2. Запустите: python get_file_id.py
3. Отправьте файл боту
4. Скопируйте file_id из ответа
5. Остановите скрипт (Ctrl+C)
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command

# ============================================================
# НАСТРОЙКИ
# ============================================================

# 👇 ВСТАВЬТЕ ТОКЕН ВАШЕГО БОТА СЮДА
BOT_TOKEN = "7864463164:AAGH9OqDL1vNUD7p2sN-uz6ThQXEbkY-M2I"

# ============================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Отправь мне любой файл (фото, документ, видео, аудио),\n"
        "и я верну тебе его <b>file_id</b>\n\n"
        "📎 Поддерживаемые типы:\n"
        "• Фото\n"
        "• Документы (PDF, DOCX и др.)\n"
        "• Видео\n"
        "• Аудио\n"
        "• Стикеры\n"
        "• Анимации (GIF)",
        parse_mode="HTML"
    )

@dp.message(F.photo)
async def get_photo_id(message: Message):
    file_id = message.photo[-1].file_id
    file_size = message.photo[-1].file_size
    
    await message.answer(
        f"📸 <b>ФОТО</b>\n\n"
        f"File ID:\n"
        f"<code>{file_id}</code>\n\n"
        f"Размер: {file_size / 1024:.1f} KB\n\n"
        f"✅ Нажми на ID чтобы скопировать",
        parse_mode="HTML"
    )
    print(f"\n{'='*60}")
    print(f"📸 PHOTO FILE_ID: {file_id}")
    print(f"{'='*60}\n")

@dp.message(F.document)
async def get_document_id(message: Message):
    file_id = message.document.file_id
    file_name = message.document.file_name
    file_size = message.document.file_size
    
    await message.answer(
        f"📄 <b>ДОКУМЕНТ</b>\n\n"
        f"Имя: <b>{file_name}</b>\n\n"
        f"File ID:\n"
        f"<code>{file_id}</code>\n\n"
        f"Размер: {file_size / 1024:.1f} KB\n\n"
        f"✅ Нажми на ID чтобы скопировать",
        parse_mode="HTML"
    )
    print(f"\n{'='*60}")
    print(f"📄 DOCUMENT FILE_ID: {file_id}")
    print(f"   Name: {file_name}")
    print(f"{'='*60}\n")

@dp.message(F.video)
async def get_video_id(message: Message):
    file_id = message.video.file_id
    duration = message.video.duration
    file_size = message.video.file_size
    
    await message.answer(
        f"🎥 <b>ВИДЕО</b>\n\n"
        f"File ID:\n"
        f"<code>{file_id}</code>\n\n"
        f"Длительность: {duration} сек\n"
        f"Размер: {file_size / 1024 / 1024:.1f} MB\n\n"
        f"✅ Нажми на ID чтобы скопировать",
        parse_mode="HTML"
    )
    print(f"\n{'='*60}")
    print(f"🎥 VIDEO FILE_ID: {file_id}")
    print(f"{'='*60}\n")

@dp.message(F.audio)
async def get_audio_id(message: Message):
    file_id = message.audio.file_id
    title = message.audio.title or "Без названия"
    performer = message.audio.performer or "Неизвестен"
    
    await message.answer(
        f"🎵 <b>АУДИО</b>\n\n"
        f"Исполнитель: {performer}\n"
        f"Название: {title}\n\n"
        f"File ID:\n"
        f"<code>{file_id}</code>\n\n"
        f"✅ Нажми на ID чтобы скопировать",
        parse_mode="HTML"
    )
    print(f"\n{'='*60}")
    print(f"🎵 AUDIO FILE_ID: {file_id}")
    print(f"{'='*60}\n")

@dp.message(F.voice)
async def get_voice_id(message: Message):
    file_id = message.voice.file_id
    duration = message.voice.duration
    
    await message.answer(
        f"🎤 <b>ГОЛОСОВОЕ СООБЩЕНИЕ</b>\n\n"
        f"File ID:\n"
        f"<code>{file_id}</code>\n\n"
        f"Длительность: {duration} сек\n\n"
        f"✅ Нажми на ID чтобы скопировать",
        parse_mode="HTML"
    )
    print(f"\n{'='*60}")
    print(f"🎤 VOICE FILE_ID: {file_id}")
    print(f"{'='*60}\n")

@dp.message(F.sticker)
async def get_sticker_id(message: Message):
    file_id = message.sticker.file_id
    emoji = message.sticker.emoji
    
    await message.answer(
        f"🎭 <b>СТИКЕР</b> {emoji}\n\n"
        f"File ID:\n"
        f"<code>{file_id}</code>\n\n"
        f"✅ Нажми на ID чтобы скопировать",
        parse_mode="HTML"
    )
    print(f"\n{'='*60}")
    print(f"🎭 STICKER FILE_ID: {file_id}")
    print(f"{'='*60}\n")

@dp.message(F.animation)
async def get_animation_id(message: Message):
    file_id = message.animation.file_id
    
    await message.answer(
        f"🎞 <b>АНИМАЦИЯ (GIF)</b>\n\n"
        f"File ID:\n"
        f"<code>{file_id}</code>\n\n"
        f"✅ Нажми на ID чтобы скопировать",
        parse_mode="HTML"
    )
    print(f"\n{'='*60}")
    print(f"🎞 ANIMATION FILE_ID: {file_id}")
    print(f"{'='*60}\n")

async def main():
    print("\n" + "="*60)
    print("🤖 БОТ ДЛЯ ПОЛУЧЕНИЯ FILE_ID ЗАПУЩЕН")
    print("="*60)
    print("\n📱 Отправьте файл боту в Telegram")
    print("📋 File ID будет выведен здесь и в чате\n")
    print("⛔ Для остановки нажмите Ctrl+C\n")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✅ Бот остановлен")
