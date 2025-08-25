import random
import string
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import (
    get_cancel_kb, get_admin_menu_kb, get_main_menu_kb, 
    get_excel_export_kb, get_broadcast_type_kb, get_system_management_kb, get_back_to_menu_kb
)
from utils.excel_exporter import ExcelExporter
from utils.csv_exporter import CSVExporter
from datetime import datetime
import asyncio

from src.database.db_init import db

admin_router = Router()

class ActivationStates(StatesGroup):
    waiting_for_code = State()

class ExportStates(StatesGroup):
    choosing_export_type = State()

class BroadcastStates(StatesGroup):
    choosing_broadcast_type = State()
    choosing_content_type = State()
    waiting_for_message = State()
    waiting_for_media = State()
    waiting_for_caption = State()

class SystemStates(StatesGroup):
    in_system_menu = State()

class ViewFeedbackStates(StatesGroup):
    viewing_feedback = State()
    viewing_detailed = State()
    
class PollStates(StatesGroup):
    poll_menu = State()
    creating_title = State()
    creating_description = State()
    adding_questions = State()
    entering_question = State()
    setting_answer_type = State()
    entering_options = State()
    confirming_poll = State()
    viewing_polls = State()
    adding_thank_you_video = State()
    viewing_results = State()
    choosing_recipients = State() 
    
class ContainerPhotoStates(StatesGroup):
    menu = State()
    adding_photo = State()
    waiting_for_number = State()
    waiting_for_description = State()
    deleting_photo = State()
    viewing_photos = State()
    
def get_container_photos_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="📷 Добавить фото контейнера")],
        [KeyboardButton(text="🗑️ Удалить фото контейнера")],
        [KeyboardButton(text="📋 Список всех фото")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# Обновите клавиатуру системного управления:
def get_system_management_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="🔄 Обновить векторную БД")],
        [KeyboardButton(text="🗑️ Очистить старые логи")],
        [KeyboardButton(text="📊 Системная информация")],
        [KeyboardButton(text="🧪 Управление фото контейнеров")],  # НОВАЯ КНОПКА
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# Добавьте обработчики:
@admin_router.message(SystemStates.in_system_menu, F.text == "🧪 Управление фото контейнеров")
async def manage_container_photos(message: Message, state: FSMContext):
    await message.answer(
        "🧪 Управление фото контейнеров\n\n"
        "Здесь вы можете добавлять и удалять фото пробирок для автоматического показа при выборе теста.",
        reply_markup=get_container_photos_kb()
    )
    await state.set_state(ContainerPhotoStates.menu)

@admin_router.message(ContainerPhotoStates.menu, F.text == "📷 Добавить фото контейнера")
async def start_add_photo(message: Message, state: FSMContext):
    await message.answer(
        "📷 Добавление фото контейнера\n\n"
        "Отправьте фото пробирки/контейнера:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(ContainerPhotoStates.adding_photo)

@admin_router.message(ContainerPhotoStates.adding_photo, F.photo)
async def receive_container_photo(message: Message, state: FSMContext):
    # Сохраняем file_id фото
    photo = message.photo[-1]  # Берем лучшее качество
    file_id = photo.file_id
    
    await state.update_data(photo_file_id=file_id)
    
    await message.answer(
        "📝 Введите номера контейнеров через запятую\n"
        "(например: 800, 801, 842, 847, 908)\n\n"
        "Или введите диапазон через дефис (например: 800-810):",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(ContainerPhotoStates.waiting_for_number)

@admin_router.message(ContainerPhotoStates.waiting_for_number)
async def receive_container_numbers(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    # Парсим введенные номера
    numbers = []
    parts = message.text.replace(' ', '').split(',')
    
    for part in parts:
        part = part.strip()
        
        # Проверяем, не диапазон ли это
        if '-' in part:
            try:
                start, end = part.split('-')
                start_num = int(start)
                end_num = int(end)
                numbers.extend(range(start_num, end_num + 1))
            except:
                await message.answer(f"❌ Неверный формат диапазона: {part}\nПопробуйте еще раз:")
                return
        else:
            # Обычное число
            try:
                numbers.append(int(part))
            except:
                await message.answer(f"❌ Неверный номер: {part}\nВведите числа через запятую:")
                return
    
    if not numbers:
        await message.answer("❌ Не удалось распознать номера. Попробуйте еще раз:")
        return
    
    # Убираем дубликаты и сортируем
    numbers = sorted(list(set(numbers)))
    
    await state.update_data(container_numbers=numbers)
    
    # Показываем, что будет сохранено
    preview = f"📦 Будут обновлены контейнеры ({len(numbers)} шт.):\n"
    if len(numbers) <= 20:
        preview += ", ".join(str(n) for n in numbers)
    else:
        preview += ", ".join(str(n) for n in numbers[:10])
        preview += f"... и еще {len(numbers)-10} номеров"
    
    preview += "\n\n📝 Введите описание для этих контейнеров\n(например: 'Пробирка с красной крышкой, с ГЕЛЕМ'):"
    
    await message.answer(preview, reply_markup=get_back_to_menu_kb())
    await state.set_state(ContainerPhotoStates.waiting_for_description)

@admin_router.message(ContainerPhotoStates.waiting_for_description)
async def save_container_photos_batch(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    data = await state.get_data()
    container_numbers = data['container_numbers']
    file_id = data['photo_file_id']
    description = message.text if message.text != "-" else None
    
    # Показываем прогресс
    progress_msg = await message.answer(f"⏳ Сохраняю фото для {len(container_numbers)} контейнеров...")
    
    success_count = 0
    failed_count = 0
    
    # Сохраняем для каждого номера
    for num in container_numbers:
        try:
            success = await db.add_container_photo(
                container_number=num,
                file_id=file_id,
                uploaded_by=message.from_user.id,
                description=description
            )
            if success:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            print(f"Error saving container {num}: {e}")
            failed_count += 1
    
    await progress_msg.delete()
    
    # Результат
    result = f"✅ Готово!\n\n"
    result += f"📸 Успешно сохранено: {success_count} контейнеров\n"
    if failed_count > 0:
        result += f"❌ Ошибки: {failed_count} контейнеров\n"
    
    if description:
        result += f"\n📝 Описание: {description}"
    
    await message.answer(result, reply_markup=get_container_photos_kb())
    
    # Показываем статистику
    containers_without = await db.get_containers_without_photos()
    if containers_without:
        await message.answer(
            f"ℹ️ Осталось контейнеров без фото: {len(containers_without)}",
            reply_markup=get_container_photos_kb()
        )
    else:
        await message.answer(
            "🎉 Все контейнеры теперь имеют фото!",
            reply_markup=get_container_photos_kb()
        )
    
    await state.set_state(ContainerPhotoStates.menu)

@admin_router.message(ContainerPhotoStates.waiting_for_number)
async def receive_container_number(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Введите только цифру номера контейнера:")
        return
    
    container_number = int(message.text)
    await state.update_data(container_number=container_number)
    
    # Запрашиваем описание
    await message.answer(
        f"📝 Введите описание для контейнера №{container_number}\n"
        f"(например: 'Пробирка с красной крышкой для биохимии')\n\n"
        f"Или отправьте '-' чтобы пропустить описание:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(ContainerPhotoStates.waiting_for_description)
    
@admin_router.message(F.text == "🔧 Создать таблицу фото")
async def create_photos_table(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user['role'] != 'admin':
        return
    
    try:
        await db.create_tables()  # Это создаст недостающие таблицы
        await message.answer("✅ Таблица container_photos создана!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@admin_router.message(ContainerPhotoStates.waiting_for_description)
async def save_container_photo_with_description(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    data = await state.get_data()
    container_number = data['container_number']
    file_id = data['photo_file_id']
    
    # Получаем описание
    description = None if message.text == "-" else message.text
    
    # Сохраняем в БД
    success = await db.add_container_photo(
        container_number=container_number,
        file_id=file_id,
        uploaded_by=message.from_user.id,
        description=description
    )
    
    if success:
        desc_text = f"\n📝 Описание: {description}" if description else ""
        await message.answer(
            f"✅ Фото для контейнера №{container_number} успешно сохранено!{desc_text}",
            reply_markup=get_container_photos_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении фото",
            reply_markup=get_container_photos_kb()
        )
    
    await state.set_state(ContainerPhotoStates.menu)

@admin_router.message(ContainerPhotoStates.menu, F.text == "📋 Список всех фото")
async def list_container_photos(message: Message):
    photos = await db.get_all_container_photos()
    
    if not photos:
        await message.answer(
            "Нет загруженных фото контейнеров.",
            reply_markup=get_container_photos_kb()
        )
        return
    
    text = "📋 Загруженные фото контейнеров:\n\n"
    for photo in photos:
        text += f"🧪 Контейнер №{photo['container_number']}\n"
        # Используем .get() с значением по умолчанию
        description = photo.get('description', 'Без описания')
        text += f"   {description}\n"
        text += f"   📅 {photo.get('upload_date', 'Дата не указана')}\n\n"
    
    await message.answer(text, reply_markup=get_container_photos_kb())
    
    # Показываем сами фото
    from bot.handlers import bot
    for photo in photos[:5]:  # Показываем первые 5
        try:
            # Также используем .get() для caption
            description = photo.get('description', 'Без описания')
            await bot.send_photo(
                message.chat.id,
                photo=photo['file_id'],
                caption=f"Контейнер №{photo['container_number']}: {description}"
            )
        except:
            pass

@admin_router.message(ContainerPhotoStates.menu, F.text == "🗑️ Удалить фото контейнера")
async def start_delete_photo(message: Message, state: FSMContext):
    photos = await db.get_all_container_photos()
    
    if not photos:
        await message.answer(
            "Нет фото для удаления.",
            reply_markup=get_container_photos_kb()
        )
        return
    
    text = "Введите номер контейнера для удаления фото:\n\n"
    text += "Доступные контейнеры: "
    text += ", ".join([str(p['container_number']) for p in photos])
    
    await message.answer(text, reply_markup=get_back_to_menu_kb())
    await state.set_state(ContainerPhotoStates.deleting_photo)

@admin_router.message(ContainerPhotoStates.deleting_photo)
async def delete_container_photo(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.set_state(ContainerPhotoStates.menu)
        await message.answer("Отмена удаления.", reply_markup=get_container_photos_kb())
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Введите номер контейнера (цифру):")
        return
    
    container_number = int(message.text)
    success = await db.delete_container_photo(container_number)
    
    if success:
        await message.answer(
            f"✅ Фото контейнера №{container_number} удалено",
            reply_markup=get_container_photos_kb()
        )
    else:
        await message.answer(
            f"❌ Контейнер №{container_number} не найден",
            reply_markup=get_container_photos_kb()
        )
    
    await state.set_state(ContainerPhotoStates.menu)

@admin_router.message(ContainerPhotoStates.menu, F.text == "🔙 Назад")
async def back_from_container_photos(message: Message, state: FSMContext):
    await state.set_state(SystemStates.in_system_menu)
    await message.answer(
        "🔧 Управление системой",
        reply_markup=get_system_management_kb()
    )    

@admin_router.message(PollStates.adding_thank_you_video)
async def handle_thank_you_video(message: Message, state: FSMContext):
    if message.text == "➡️ Пропустить":
        # Переходим к выбору получателей
        await message.answer(
            "Кому отправить опрос?",
            reply_markup=get_broadcast_type_kb()
        )
        await state.set_state(PollStates.choosing_recipients)
        
    elif message.text == "🎬 Добавить медиа" or message.text == "🎬 Добавить видео":
        await message.answer(
            "📎 Отправьте видео или GIF для благодарственного сообщения:\n\n"
            "Поддерживаемые форматы:\n"
            "• MP4 видео\n"
            "• Анимированные GIF\n",
            reply_markup=get_back_to_menu_kb()
        )
        
    # Автоматически определяем тип медиа
    elif message.video:
        # Это видео
        data = await state.get_data()
        poll_id = data['created_poll_id']
        
        await db.update_poll_media(poll_id, message.video.file_id, 'video')
        
        await message.answer(
            "✅ Видео добавлено!\n\nКому отправить опрос?",
            reply_markup=get_broadcast_type_kb()
        )
        await state.set_state(PollStates.choosing_recipients)
        
    elif message.animation:
        # Это GIF
        data = await state.get_data()
        poll_id = data['created_poll_id']
        
        await db.update_poll_media(poll_id, message.animation.file_id, 'animation')
        
        await message.answer(
            "✅ GIF добавлен!\n\nКому отправить опрос?",
            reply_markup=get_broadcast_type_kb()
        )
        await state.set_state(PollStates.choosing_recipients)
        
    elif message.document:
        # Проверяем, не GIF ли это в виде документа
        if message.document.mime_type and 'gif' in message.document.mime_type.lower():
            data = await state.get_data()
            poll_id = data['created_poll_id']
            
            await db.update_poll_media(poll_id, message.document.file_id, 'document_gif')
            
            await message.answer(
                "✅ GIF (документ) добавлен!\n\nКому отправить опрос?",
                reply_markup=get_broadcast_type_kb()
            )
            await state.set_state(PollStates.choosing_recipients)
        else:
            await message.answer(
                "❌ Пожалуйста, отправьте видео или GIF.\n"
                "Или нажмите 'Пропустить' для продолжения без медиа.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="🎬 Добавить видео")],
                        [KeyboardButton(text="➡️ Пропустить")]
                    ],
                    resize_keyboard=True
                )
            )
    
    else:
        await message.answer(
            "Пожалуйста, отправьте видео/GIF или нажмите 'Пропустить'",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🎬 Добавить видео")],
                    [KeyboardButton(text="➡️ Пропустить")]
                ],
                resize_keyboard=True
            )
        )

@admin_router.message(PollStates.adding_questions)
async def handle_poll_questions(message: Message, state: FSMContext):
    if message.text == "❌ Отменить создание":
        await state.clear()
        await message.answer("Создание опроса отменено.", reply_markup=get_admin_menu_kb())
        return
    
    elif message.text == "➕ Добавить вопрос":
        await message.answer(
            "Введите текст вопроса:",
            reply_markup=get_back_to_menu_kb()
        )
        await state.set_state(PollStates.entering_question)
    
    elif message.text == "✅ Завершить создание":
        data = await state.get_data()
        questions = data.get('poll_questions', [])
        
        if not questions:
            await message.answer(
                "❌ Опрос должен содержать хотя бы один вопрос!",
                reply_markup=get_poll_creation_kb()
            )
            return
        
        # Создаем опрос в БД
        poll_id = await db.create_poll(
            title=data['poll_title'],
            description=data.get('poll_description'),
            questions=questions,
            created_by=message.from_user.id
        )

        # Сохраняем данные опроса для рассылки
        await state.update_data(
            created_poll_id=poll_id,
            created_poll_title=data['poll_title']
        )

        # Спрашиваем про видео
        await message.answer(
            f"✅ Опрос '{data['poll_title']}' создан!\n\n"
            "Хотите добавить благодарственное медиа после опроса?\n"
            "(поддерживается видео и GIF)",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🎬 Добавить медиа")],
                    [KeyboardButton(text="➡️ Пропустить")]
                ],
                resize_keyboard=True
            )
        )
        await state.set_state(PollStates.adding_thank_you_video)
        return  

@admin_router.message(PollStates.choosing_recipients)
async def send_poll_to_users(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Опрос создан, но не отправлен.", reply_markup=get_admin_menu_kb())
        return
    
    broadcast_types = {
        "📢 Всем пользователям": "all",
        "👨‍⚕️ Только клиентам": "clients",
        "🔬 Только сотрудникам": "employees"
    }
    
    if message.text not in broadcast_types:
        await message.answer(
            "Выберите тип рассылки из предложенных вариантов.",
            reply_markup=get_broadcast_type_kb()
        )
        return
    
    broadcast_type = broadcast_types[message.text]
    recipients = await db.get_broadcast_recipients(broadcast_type)
    
    if not recipients:
        await message.answer(
            "❌ Не найдено получателей для рассылки.",
            reply_markup=get_admin_menu_kb()
        )
        await state.clear()
        return
    
    loading_msg = await message.answer(f"📤 Отправляю опрос {len(recipients)} пользователям...")
    
    data = await state.get_data()
    poll_id = data['created_poll_id']
    poll_title = data['created_poll_title']
    
    # Отправляем опрос пользователям
    from bot.handlers import bot
    from bot.handlers.poll_sender import send_poll_to_user
    
    success_count = 0
    failed_count = 0
    
    for user_id in recipients:
        try:
            await send_poll_to_user(bot, user_id, poll_id)
            success_count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            failed_count += 1
            print(f"Failed to send poll to {user_id}: {e}")
    
    await loading_msg.delete()
    await message.answer(
        f"✅ Опрос отправлен!\n\n"
        f"📤 Успешно: {success_count}\n"
        f"❌ Неудачно: {failed_count}",
        reply_markup=get_admin_menu_kb()
    )
    await state.clear()

# Добавляем клавиатуры для опросов
def get_poll_management_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="📝 Создать опрос")],
        [KeyboardButton(text="📊 Активные опросы")],
        [KeyboardButton(text="📈 Результаты опросов")],
        [KeyboardButton(text="📥 Выгрузить результаты")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_poll_answer_type_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="📝 Текстовый ответ")],
        [KeyboardButton(text="☑️ Один вариант")],
        [KeyboardButton(text="✅ Несколько вариантов")],
        [KeyboardButton(text="⭐ Оценка (1-5)")],
        [KeyboardButton(text="🔙 Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_poll_creation_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="➕ Добавить вопрос")],
        [KeyboardButton(text="✅ Завершить создание")],
        [KeyboardButton(text="❌ Отменить создание")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@admin_router.message(F.text == "📋 Опросы")
async def poll_management(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    await message.answer(
        "📋 Управление опросами\n\n"
        "Здесь вы можете создавать опросы, просматривать результаты и выгружать статистику.",
        reply_markup=get_poll_management_kb()
    )
    await state.set_state(PollStates.poll_menu)

@admin_router.message(PollStates.poll_menu, F.text == "📝 Создать опрос")
async def create_poll_start(message: Message, state: FSMContext):
    await message.answer(
        "📝 Создание нового опроса\n\n"
        "Введите название опроса:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(PollStates.creating_title)

@admin_router.message(PollStates.creating_title)
async def create_poll_title(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    await state.update_data(poll_title=message.text)
    await message.answer(
        "Введите описание опроса (или отправьте '-' для пропуска):",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(PollStates.creating_description)

@admin_router.message(PollStates.creating_description)
async def create_poll_description(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    description = None if message.text == "-" else message.text
    await state.update_data(poll_description=description, poll_questions=[])
    
    await message.answer(
        "Теперь добавим вопросы к опросу.",
        reply_markup=get_poll_creation_kb()
    )
    await state.set_state(PollStates.adding_questions)


@admin_router.message(PollStates.entering_question)
async def enter_question_text(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.set_state(PollStates.adding_questions)
        await message.answer(
            "Добавление вопроса отменено.",
            reply_markup=get_poll_creation_kb()
        )
        return
    
    await state.update_data(current_question_text=message.text)
    await message.answer(
        "Выберите тип ответа на этот вопрос:",
        reply_markup=get_poll_answer_type_kb()
    )
    await state.set_state(PollStates.setting_answer_type)

@admin_router.message(PollStates.setting_answer_type)
async def set_answer_type(message: Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.set_state(PollStates.adding_questions)
        await message.answer(
            "Добавление вопроса отменено.",
            reply_markup=get_poll_creation_kb()
        )
        return
    
    answer_types = {
        "📝 Текстовый ответ": "text",
        "☑️ Один вариант": "single",
        "✅ Несколько вариантов": "multiple",
        "⭐ Оценка (1-5)": "rating"
    }
    
    if message.text not in answer_types:
        await message.answer(
            "Выберите тип ответа из предложенных вариантов.",
            reply_markup=get_poll_answer_type_kb()
        )
        return
    
    answer_type = answer_types[message.text]
    await state.update_data(current_answer_type=answer_type)
    
    if answer_type in ["single", "multiple"]:
        await message.answer(
            "Введите варианты ответов через запятую:\n"
            "Например: Да, Нет, Не знаю",
            reply_markup=get_back_to_menu_kb()
        )
        await state.set_state(PollStates.entering_options)
    else:
        # Для текстовых ответов и рейтинга сразу сохраняем вопрос
        data = await state.get_data()
        questions = data.get('poll_questions', [])
        
        new_question = {
            'text': data['current_question_text'],
            'type': answer_type,
            'options': None
        }
        questions.append(new_question)
        
        await state.update_data(poll_questions=questions)
        await message.answer(
            f"✅ Вопрос добавлен! Всего вопросов: {len(questions)}",
            reply_markup=get_poll_creation_kb()
        )
        await state.set_state(PollStates.adding_questions)

@admin_router.message(PollStates.entering_options)
async def enter_options(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.set_state(PollStates.adding_questions)
        await message.answer(
            "Добавление вопроса отменено.",
            reply_markup=get_poll_creation_kb()
        )
        return
    
    options = [opt.strip() for opt in message.text.split(',')]
    
    if len(options) < 2:
        await message.answer(
            "❌ Необходимо указать минимум 2 варианта ответа.\n"
            "Введите варианты через запятую:",
            reply_markup=get_back_to_menu_kb()
        )
        return
    
    data = await state.get_data()
    questions = data.get('poll_questions', [])
    
    new_question = {
        'text': data['current_question_text'],
        'type': data['current_answer_type'],
        'options': options
    }
    questions.append(new_question)
    
    await state.update_data(poll_questions=questions)
    await message.answer(
        f"✅ Вопрос добавлен! Всего вопросов: {len(questions)}",
        reply_markup=get_poll_creation_kb()
    )
    await state.set_state(PollStates.adding_questions)

@admin_router.message(PollStates.poll_menu, F.text == "📊 Активные опросы")
async def view_active_polls(message: Message):
    polls = await db.get_active_polls()
    
    if not polls:
        await message.answer(
            "Нет активных опросов.",
            reply_markup=get_poll_management_kb()
        )
        return
    
    text = "📊 Активные опросы:\n\n"
    for poll in polls:
        text += f"🔸 {poll['title']}\n"
        text += f"   ID: {poll['id']}\n"
        text += f"   Вопросов: {poll['questions_count']}\n"
        text += f"   Ответов: {poll['responses_count']}\n"
        text += f"   Создан: {poll['created_at']}\n\n"
    
    await message.answer(text, reply_markup=get_poll_management_kb())

@admin_router.message(PollStates.poll_menu, F.text == "📈 Результаты опросов")
async def view_poll_results(message: Message, state: FSMContext):
    polls = await db.get_polls_with_results()
    
    if not polls:
        await message.answer(
            "Нет опросов с результатами.",
            reply_markup=get_poll_management_kb()
        )
        return
    
    text = "📈 Результаты опросов:\n\n"
    for poll in polls:
        text += f"📊 {poll['title']}\n"
        text += f"Участников: {poll['total_responses']}\n"
        
        # Показываем краткую статистику по каждому вопросу
        for q_idx, question in enumerate(poll['questions'], 1):
            text += f"\n{q_idx}. {question['text']}\n"
            
            if question['type'] == 'rating':
                avg_rating = question.get('avg_rating', 0)
                text += f"   Средняя оценка: ⭐ {avg_rating:.1f}\n"
            elif question['type'] in ['single', 'multiple']:
                top_answer = question.get('top_answer', 'Нет ответов')
                text += f"   Популярный ответ: {top_answer}\n"
            else:
                text += f"   Ответов: {question.get('answer_count', 0)}\n"
        
        text += "─" * 30 + "\n"
    
    await message.answer(text, reply_markup=get_poll_management_kb())

@admin_router.message(PollStates.poll_menu, F.text == "📥 Выгрузить результаты")
async def export_poll_results(message: Message):
    loading_msg = await message.answer("⏳ Подготавливаю выгрузку результатов опросов...")
    
    try:
        # Получаем все результаты опросов
        polls_data = await db.get_full_poll_results()
        
        if not polls_data:
            await loading_msg.delete()
            await message.answer(
                "Нет данных для выгрузки.",
                reply_markup=get_poll_management_kb()
            )
            return
        
        # Создаем Excel файл с результатами
        from utils.poll_exporter import PollExporter
        exporter = PollExporter()
        excel_data = await exporter.export_polls_to_excel(polls_data)
        
        filename = f"poll_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await loading_msg.delete()
        await message.answer_document(
            BufferedInputFile(excel_data, filename),
            caption=f"📊 Результаты опросов\n📅 Дата выгрузки: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=get_poll_management_kb()
        )
        
    except Exception as e:
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при выгрузке: {str(e)}",
            reply_markup=get_poll_management_kb()
        )

@admin_router.message(PollStates.poll_menu, F.text == "🔙 Назад")
async def back_from_polls(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Главное меню администратора",
        reply_markup=get_admin_menu_kb()
    )

# Добавим новую функцию для клавиатуры выбора типа контента
def get_broadcast_content_type_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="📝 Текстовое сообщение")],
        [KeyboardButton(text="🖼️ Изображение")],
        [KeyboardButton(text="🎬 Видео")],
        [KeyboardButton(text="🎭 GIF")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_feedback_navigation_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="⬅️ Предыдущее"), KeyboardButton(text="➡️ Следующее")],
        [KeyboardButton(text="📎 Показать медиа")],
        [KeyboardButton(text="🔙 Назад к списку")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@admin_router.message(F.text == "🔑 Активировать код")
async def start_activation(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Необходимо пройти регистрацию. Используйте /start")
        return
    
    if user['role'] == 'admin':
        await message.answer(
            "Вы уже являетесь администратором!",
            reply_markup=get_admin_menu_kb()
        )
        return
    
    await message.answer(
        "Введите код активации администратора:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(ActivationStates.waiting_for_code)

@admin_router.message(ActivationStates.waiting_for_code)
async def process_activation_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_main_menu_kb())
        return
    
    code = message.text.strip().upper()
    activation = await db.check_activation_code(code)
    
    if activation:
        await db.use_activation_code(code, user_id)
        await db.update_user_role(user_id, 'admin')
        
        await message.answer(
            "✅ Код успешно активирован!\n"
            "Теперь вы администратор системы.",
            reply_markup=get_admin_menu_kb()
        )
    else:
        await message.answer(
            "❌ Неверный или уже использованный код.\n"
            "Попробуйте еще раз или нажмите Отмена.",
            reply_markup=get_back_to_menu_kb()
        )
        return
    
    await state.clear()

@admin_router.message(F.text == "🔐 Создать код")
async def create_code(message: Message):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    admin_code = f"ADMIN{code}"
    
    await db.create_admin_code(admin_code)
    
    await message.answer(
        "✅ Код активации создан:\n\n"
        f"👨‍💼 Для администратора: `{admin_code}`\n\n"
        "Код одноразовый и действует бессрочно.",
        parse_mode="Markdown",
        reply_markup=get_admin_menu_kb()
    )

@admin_router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    stats = await db.get_statistics()
    
    await message.answer(
        f"📊 Статистика системы:\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"├ Клиентов: {stats['clients']}\n"
        f"├ Сотрудников: {stats['employees']}\n"
        f"└ Администраторов: {stats['admins']}\n\n"
        f"📋 Обращений: {stats['total_requests']}\n"
        f"❓ Вопросов: {stats['questions']}\n"
        f"📞 Звонков: {stats['callbacks']}\n"
        f"💡 Предложений: {stats['suggestions']}\n"
        f"⚠️ Жалоб: {stats['complaints']}",
        reply_markup=get_admin_menu_kb()
    )

@admin_router.message(F.text == "📥 Выгрузка в Excel")
async def start_excel_export(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    await message.answer(
        "Выберите тип выгрузки:",
        reply_markup=get_excel_export_kb()
    )
    await state.set_state(ExportStates.choosing_export_type)

@admin_router.message(ExportStates.choosing_export_type)
async def process_export_choice(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    loading_msg = await message.answer("⏳ Подготавливаю файл для выгрузки...")
    
    try:
        exporter = ExcelExporter(db.db_path)
        csv_exporter = CSVExporter(db.db_path)
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        if message.text == "📊 Полная выгрузка":
            try:
                excel_data = await exporter.export_all_data()
                filename = f"full_{filename}"
                caption = "📊 Полная выгрузка данных системы"
            except Exception as excel_error:
                print(f"[WARNING] Excel export failed, using CSV backup: {excel_error}")
                excel_data = await csv_exporter.export_all_data_csv()
                filename = f"full_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                caption = "📊 Полная выгрузка данных системы (CSV резерв)"
        
        elif message.text == "👥 Только пользователи":
            excel_data = await exporter.export_users()
            filename = f"users_{filename}"
            caption = "👥 Выгрузка пользователей"
        
        elif message.text == "❓ Только вопросы":
            excel_data = await exporter.export_questions()
            filename = f"questions_{filename}"
            caption = "❓ Выгрузка вопросов"
        
        elif message.text == "📞 Только звонки":
            excel_data = await exporter.export_callbacks()
            filename = f"callbacks_{filename}"
            caption = "📞 Выгрузка запросов на звонок"
        
        elif message.text == "💡 Только обратная связь":
            excel_data = await exporter.export_feedback()
            filename = f"feedback_{filename}"
            caption = "💡 Выгрузка обратной связи"
        
        else:
            await loading_msg.delete()
            await message.answer(
                "Неизвестный тип выгрузки. Выберите из предложенных вариантов.",
                reply_markup=get_excel_export_kb()
            )
            return
        
        await loading_msg.delete()
        
        await message.answer_document(
            BufferedInputFile(excel_data, filename),
            caption=f"{caption}\n📅 Дата выгрузки: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=get_admin_menu_kb()
        )
        
        await state.clear()
        
    except Exception as e:
        print(f"[ERROR] Excel export failed: {e}")
        import traceback
        traceback.print_exc()
        
        await loading_msg.delete()
        
        # Более детальная информация об ошибке для администратора
        error_details = str(e)
        if "xlsxwriter" in error_details.lower():
            error_msg = "❌ Ошибка: отсутствует библиотека xlsxwriter. Обратитесь к разработчику."
        elif "database" in error_details.lower() or "sqlite" in error_details.lower():
            error_msg = "❌ Ошибка доступа к базе данных. Попробуйте позже."
        elif "permission" in error_details.lower():
            error_msg = "❌ Ошибка доступа к файлам. Проверьте права доступа."
        else:
            error_msg = f"❌ Ошибка при создании выгрузки: {error_details[:100]}..."
        
        await message.answer(error_msg, reply_markup=get_admin_menu_kb())
        await state.clear()

@admin_router.message(F.text == "📢 Рассылка")
async def start_broadcast(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    await message.answer(
        "Выберите получателей рассылки:",
        reply_markup=get_broadcast_type_kb()
    )
    await state.set_state(BroadcastStates.choosing_broadcast_type)

@admin_router.message(BroadcastStates.choosing_broadcast_type)
async def process_broadcast_type(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    broadcast_types = {
        "📢 Всем пользователям": "all",
        "👨‍⚕️ Только клиентам": "clients",
        "🔬 Только сотрудникам": "employees"
    }
    
    if message.text not in broadcast_types:
        await message.answer(
            "Выберите тип рассылки из предложенных вариантов.",
            reply_markup=get_broadcast_type_kb()
        )
        return
    
    await state.update_data(broadcast_type=broadcast_types[message.text])
    await message.answer(
        "Выберите тип контента для рассылки:",
        reply_markup=get_broadcast_content_type_kb()
    )
    await state.set_state(BroadcastStates.choosing_content_type)

@admin_router.message(BroadcastStates.choosing_content_type)
async def process_content_type(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    if message.text == "📝 Текстовое сообщение":
        await state.update_data(content_type="text")
        await message.answer(
            "📝 Введите текст сообщения для рассылки:\n\n"
            "Поддерживается HTML-форматирование:\n"
            "• <b>жирный</b>\n"
            "• <i>курсив</i>\n"
            "• <code>код</code>",
            reply_markup=get_back_to_menu_kb()
        )
        await state.set_state(BroadcastStates.waiting_for_message)
    
    elif message.text in ["🖼️ Изображение", "🎬 Видео", "🎭 GIF"]:
        content_types = {
            "🖼️ Изображение": "photo",
            "🎬 Видео": "video",
            "🎭 GIF": "animation"
        }
        await state.update_data(content_type=content_types[message.text])
        
        media_type = message.text.split()[1].lower()
        await message.answer(
            f"📎 Отправьте {media_type} для рассылки:",
            reply_markup=get_back_to_menu_kb()
        )
        await state.set_state(BroadcastStates.waiting_for_media)
    
    else:
        await message.answer(
            "Выберите тип контента из предложенных вариантов.",
            reply_markup=get_broadcast_content_type_kb()
        )

@admin_router.message(BroadcastStates.waiting_for_media)
async def process_media(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    data = await state.get_data()
    content_type = data.get('content_type')
    
    # Проверяем тип полученного медиа
    if content_type == "photo" and message.photo:
        file_id = message.photo[-1].file_id  # Берем фото в лучшем качестве
        await state.update_data(file_id=file_id)
    elif content_type == "video" and message.video:
        file_id = message.video.file_id
        await state.update_data(file_id=file_id)
    elif content_type == "animation" and message.animation:
        file_id = message.animation.file_id
        await state.update_data(file_id=file_id)
    else:
        await message.answer(
            f"❌ Ожидается {'фото' if content_type == 'photo' else 'видео' if content_type == 'video' else 'GIF'}. "
            "Попробуйте еще раз или нажмите 'Вернуться в главное меню'.",
            reply_markup=get_back_to_menu_kb()
        )
        return
    
    await message.answer(
        "📝 Теперь введите подпись к медиафайлу (или отправьте '-' без подписи):\n\n"
        "Поддерживается HTML-форматирование:\n"
        "• <b>жирный</b>\n"
        "• <i>курсив</i>\n"
        "• <code>код</code>",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(BroadcastStates.waiting_for_caption)

@admin_router.message(BroadcastStates.waiting_for_caption)
async def process_caption(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    caption = None if message.text == "-" else message.text
    await state.update_data(caption=caption)
    
    # Переходим к отправке
    await send_broadcast(message, state)

@admin_router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    await state.update_data(text=message.text)
    await send_broadcast(message, state)

async def send_broadcast(message: Message, state: FSMContext):
    data = await state.get_data()
    broadcast_type = data['broadcast_type']
    content_type = data.get('content_type', 'text')
    
    recipients = await db.get_broadcast_recipients(broadcast_type)
    
    if not recipients:
        await message.answer(
            "❌ Не найдено получателей для рассылки.",
            reply_markup=get_admin_menu_kb()
        )
        await state.clear()
        return
    
    # Показываем превью рассылки
    preview_text = "📢 Рассылка будет отправлена {} получателям.\n\n".format(len(recipients))
    
    if content_type == "text":
        preview_text += f"Текст сообщения:\n{data.get('text')}\n\n"
    else:
        media_types = {"photo": "Изображение", "video": "Видео", "animation": "GIF"}
        preview_text += f"Тип контента: {media_types.get(content_type)}\n"
        if data.get('caption'):
            preview_text += f"Подпись: {data.get('caption')}\n\n"
    
    preview_text += "Начинаю рассылку..."
    
    await message.answer(preview_text)
    
    from bot.handlers import bot
    success_count = 0
    failed_count = 0
    
    for recipient_id in recipients:
        try:
            if content_type == "text":
                await bot.send_message(
                    recipient_id,
                    f"📢 <b>Сообщение от группы техподдержки</b>\n\n{data.get('text')}",
                    parse_mode="HTML"
                )
            elif content_type == "photo":
                caption = f"📢 <b>Сообщение от группы техподдержки</b>\n\n{data.get('caption')}" if data.get('caption') else "📢 <b>Сообщение от группы техподдержки</b>"
                await bot.send_photo(
                    recipient_id,
                    photo=data.get('file_id'),
                    caption=caption,
                    parse_mode="HTML"
                )
            elif content_type == "video":
                caption = f"📢 <b>Сообщение от группы техподдержки</b>\n\n{data.get('caption')}" if data.get('caption') else "📢 <b>Сообщение от группы техподдержки</b>"
                await bot.send_video(
                    recipient_id,
                    video=data.get('file_id'),
                    caption=caption,
                    parse_mode="HTML"
                )
            elif content_type == "animation":
                caption = f"📢 <b>Сообщение от группы техподдержки</b>\n\n{data.get('caption')}" if data.get('caption') else "📢 <b>Сообщение от группы техподдержки</b>"
                await bot.send_animation(
                    recipient_id,
                    animation=data.get('file_id'),
                    caption=caption,
                    parse_mode="HTML"
                )
            
            success_count += 1
            await asyncio.sleep(0.1)  # Задержка между отправками
        except Exception as e:
            failed_count += 1
            print(f"Failed to send to {recipient_id}: {e}")
    
    await message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Успешно отправлено: {success_count}\n"
        f"❌ Не удалось отправить: {failed_count}",
        reply_markup=get_admin_menu_kb()
    )
    await state.clear()

@admin_router.message(F.text == "👥 Пользователи")
async def show_users(message: Message):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    users_info = await db.get_recent_users(limit=10)
    
    if not users_info:
        await message.answer(
            "Пользователей пока нет.",
            reply_markup=get_admin_menu_kb()
        )
        return
    
    text = "👥 Последние 10 зарегистрированных пользователей:\n\n"
    
    for user_data in users_info:
        # Определяем тип пользователя
        if user_data.get('user_type') == 'client':
            user_type = "👨‍⚕️ Ветеринар"
        elif user_data.get('user_type') == 'employee':
            user_type = "🔬 Сотрудник"
        else:
            user_type = "👤 Пользователь"
            
        role = " 👑" if user_data['role'] == 'admin' else ""
        
        text += f"{user_type}{role} {user_data.get('name', 'Без имени')}\n"
        text += f"🆔 {user_data['telegram_id']}\n"
        
        if user_data.get('client_code'):
            text += f"🏥 Код: {user_data['client_code']}\n"
        
        if user_data.get('specialization'):
            text += f"📋 Специализация: {user_data['specialization']}\n"
        elif user_data.get('department_function'):
            dept_map = {'laboratory': 'Лаборатория', 'sales': 'Продажи', 'support': 'Поддержка'}
            dept = dept_map.get(user_data['department_function'], user_data['department_function'])
            text += f"🏢 Функция: {dept}\n"
            if user_data.get('region'):
                text += f"📍 Регион: {user_data['region']}\n"
        
        text += f"🌍 Страна: {user_data.get('country', 'BY')}\n"
        text += f"📅 {user_data['registration_date']}\n"
        text += "─" * 30 + "\n"
    
    await message.answer(text, reply_markup=get_admin_menu_kb())

@admin_router.message(F.text == "📋 Все обращения")
async def show_all_requests(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    try:
        recent_feedback = await db.get_recent_feedback(limit=10)
        
        if not recent_feedback:
            await message.answer(
                "Обращений пока нет.",
                reply_markup=get_admin_menu_kb()
            )
            return
        
        # Сохраняем список обращений в состоянии для навигации
        await state.update_data(feedback_list=recent_feedback, current_index=0)
        
        text = "📋 Последние обращения:\n\n"
        
        for i, feedback in enumerate(recent_feedback[:5], 1):
            feedback_type = "💡 Предложение" if feedback.get('feedback_type') == 'suggestion' else "⚠️ Жалоба"
            status = {
                'new': '🆕 Новое',
                'in_progress': '⏳ В работе',
                'resolved': '✅ Решено'
            }.get(feedback.get('status', 'new'), 'new')
            
            text += f"{i}. {feedback_type} | {status}\n"
            text += f"👤 {feedback.get('user_name', 'Неизвестный')}\n"
            
            # Безопасная обработка сообщения
            message_text = feedback.get('message', 'Без текста')
            if isinstance(message_text, str):
                preview = message_text[:50] + ('...' if len(message_text) > 50 else '')
            else:
                preview = "Без текста"
            
            text += f"📝 {preview}\n"
            
            # Проверяем наличие медиа
            if feedback.get('media_type'):
                media_icons = {
                    'photo': '🖼️ Изображение',
                    'video': '🎬 Видео',
                    'animation': '🎭 GIF',
                    'document': '📄 Документ',
                    'voice': '🎤 Голосовое',
                    'audio': '🎵 Аудио'
                }
                text += f"📎 {media_icons.get(feedback['media_type'], 'Медиа')}\n"
            
            text += f"📅 {feedback.get('timestamp', 'Дата не указана')}\n"
            text += "─" * 30 + "\n"
        
        text += "\n📌 Для просмотра деталей напишите номер обращения (1-10)"
        
        await message.answer(text, reply_markup=get_admin_menu_kb())
        await state.set_state(ViewFeedbackStates.viewing_feedback)
        
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при загрузке обращений: {str(e)}",
            reply_markup=get_admin_menu_kb()
        )
        await state.clear()

@admin_router.message(ViewFeedbackStates.viewing_feedback)
async def view_feedback_detail(message: Message, state: FSMContext):
    try:
        # Проверяем, не команда ли это возврата
        if message.text in ["🔙 Назад", "📋 Все обращения", "🏠 Главное меню"]:
            await state.clear()
            await message.answer("Главное меню администратора", reply_markup=get_admin_menu_kb())
            return
        
        # Пытаемся получить номер обращения
        if message.text.isdigit():
            index = int(message.text) - 1
            data = await state.get_data()
            feedback_list = data.get('feedback_list', [])
            
            if 0 <= index < len(feedback_list):
                feedback = feedback_list[index]
                await state.update_data(current_feedback=feedback, current_index=index)
                
                # Формируем детальную информацию
                feedback_type = "💡 Предложение" if feedback.get('feedback_type') == 'suggestion' else "⚠️ Жалоба"
                status = {
                    'new': '🆕 Новое',
                    'in_progress': '⏳ В работе',
                    'resolved': '✅ Решено'
                }.get(feedback.get('status', 'new'), 'new')
                
                detail_text = f"📋 Детали обращения #{index + 1}\n\n"
                detail_text += f"Тип: {feedback_type}\n"
                detail_text += f"Статус: {status}\n"
                detail_text += f"👤 От: {feedback.get('user_name', 'Неизвестный')}\n"
                detail_text += f"🆔 ID: {feedback.get('user_id', 'Не указан')}\n"
                detail_text += f"📅 Дата: {feedback.get('timestamp', 'Не указана')}\n\n"
                detail_text += f"📝 Сообщение:\n{feedback.get('message', 'Без текста')}\n"
                
                # Если есть медиа, показываем информацию о нем
                if feedback.get('media_type'):
                    media_icons = {
                        'photo': '🖼️ Изображение',
                        'video': '🎬 Видео',
                        'animation': '🎭 GIF',
                        'document': '📄 Документ',
                        'voice': '🎤 Голосовое сообщение',
                        'audio': '🎵 Аудио'
                    }
                    detail_text += f"\n📎 Прикреплено: {media_icons.get(feedback['media_type'], 'Медиа')}"
                    
                    # Если есть file_id, можем предложить показать медиа
                    if feedback.get('media_file_id'):
                        detail_text += "\n\n💡 Используйте кнопку 'Показать медиа' для просмотра"
                
                await message.answer(detail_text, reply_markup=get_feedback_navigation_kb())
                await state.set_state(ViewFeedbackStates.viewing_detailed)
            else:
                await message.answer(
                    f"❌ Обращение с номером {message.text} не найдено.\n"
                    f"Доступны номера от 1 до {len(feedback_list)}",
                    reply_markup=get_admin_menu_kb()
                )
        else:
            await message.answer(
                "Введите номер обращения (цифру) или используйте меню для навигации.",
                reply_markup=get_admin_menu_kb()
            )
            
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при просмотре обращения: {str(e)}",
            reply_markup=get_admin_menu_kb()
        )
        await state.clear()

@admin_router.message(ViewFeedbackStates.viewing_detailed)
async def handle_feedback_navigation(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        feedback_list = data.get('feedback_list', [])
        current_index = data.get('current_index', 0)
        current_feedback = data.get('current_feedback')
        
        if message.text == "🔙 Назад к списку":
            await show_all_requests(message, state)
            return
        
        elif message.text == "⬅️ Предыдущее":
            if current_index > 0:
                current_index -= 1
                await state.update_data(current_index=current_index)
                # Рекурсивно показываем предыдущее обращение
                mock_message = Message(text=str(current_index + 1), from_user=message.from_user, chat=message.chat)
                await view_feedback_detail(mock_message, state)
            else:
                await message.answer("Это первое обращение в списке.")
        
        elif message.text == "➡️ Следующее":
            if current_index < len(feedback_list) - 1:
                current_index += 1
                await state.update_data(current_index=current_index)
                # Рекурсивно показываем следующее обращение
                mock_message = Message(text=str(current_index + 1), from_user=message.from_user, chat=message.chat)
                await view_feedback_detail(mock_message, state)
            else:
                await message.answer("Это последнее обращение в списке.")
        
        elif message.text == "📎 Показать медиа":
            if current_feedback and current_feedback.get('media_file_id'):
                try:
                    from bot.handlers import bot
                    media_type = current_feedback.get('media_type')
                    file_id = current_feedback.get('media_file_id')
                    
                    if media_type == 'photo':
                        await bot.send_photo(message.chat.id, photo=file_id, caption="📎 Прикрепленное изображение")
                    elif media_type == 'video':
                        await bot.send_video(message.chat.id, video=file_id, caption="📎 Прикрепленное видео")
                    elif media_type == 'animation':
                        await bot.send_animation(message.chat.id, animation=file_id, caption="📎 Прикрепленный GIF")
                    elif media_type == 'document':
                        await bot.send_document(message.chat.id, document=file_id, caption="📎 Прикрепленный документ")
                    elif media_type == 'voice':
                        await bot.send_voice(message.chat.id, voice=file_id, caption="📎 Голосовое сообщение")
                    elif media_type == 'audio':
                        await bot.send_audio(message.chat.id, audio=file_id, caption="📎 Аудио файл")
                    else:
                        await message.answer("❌ Неизвестный тип медиа")
                except Exception as e:
                    await message.answer(f"❌ Не удалось отправить медиа: {str(e)}")
            else:
                await message.answer("К этому обращению не прикреплено медиа.")
        
        else:
            await message.answer(
                "Используйте кнопки навигации или вернитесь к списку.",
                reply_markup=get_feedback_navigation_kb()
            )
            
    except Exception as e:
        await message.answer(
            f"❌ Ошибка навигации: {str(e)}",
            reply_markup=get_admin_menu_kb()
        )
        await state.clear()

@admin_router.message(F.text == "🔧 Управление системой")
async def system_management(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    await message.answer(
        "🔧 Управление системой",
        reply_markup=get_system_management_kb()
    )
    await state.set_state(SystemStates.in_system_menu)

@admin_router.message(SystemStates.in_system_menu)
async def handle_system_management(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        await message.answer("Главное меню администратора", reply_markup=get_admin_menu_kb())
        return
    
    elif message.text == "🔄 Обновить векторную БД":
        loading_msg = await message.answer("⏳ Обновляю векторную базу данных...")
        
        try:
            from src.data_vectorization import DataProcessor
            processor = DataProcessor()
            processor.create_vector_store(reset=True)
            
            await loading_msg.delete()
            await message.answer(
                "✅ Векторная база данных успешно обновлена!",
                reply_markup=get_system_management_kb()
            )
        except Exception as e:
            await loading_msg.delete()
            await message.answer(
                f"❌ Ошибка при обновлении: {str(e)}",
                reply_markup=get_system_management_kb()
            )
    
    elif message.text == "🗑️ Очистить старые логи":
        try:
            cleared_count = await db.clear_old_logs(days=30)
            await message.answer(
                f"✅ Очищено {cleared_count} старых записей логов (старше 30 дней)",
                reply_markup=get_system_management_kb()
            )
        except Exception as e:
            await message.answer(
                f"❌ Ошибка при очистке логов: {str(e)}",
                reply_markup=get_system_management_kb()
            )
    
    elif message.text == "📊 Системная информация":
        try:
            import psutil
            import os
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            db_size = os.path.getsize(db.db_path) / 1024 / 1024
            
            vector_db_path = "data/chroma_db"
            vector_db_size = 0
            if os.path.exists(vector_db_path):
                for dirpath, dirnames, filenames in os.walk(vector_db_path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        vector_db_size += os.path.getsize(fp)
                vector_db_size = vector_db_size / 1024 / 1024
            
            system_info = f"""
📊 Системная информация:

🖥️ Процессор: {cpu_percent}%
💾 Память: {memory.percent}% ({memory.used // 1024 // 1024} МБ / {memory.total // 1024 // 1024} МБ)
💿 Диск: {disk.percent}% ({disk.used // 1024 // 1024 // 1024} ГБ / {disk.total // 1024 // 1024 // 1024} ГБ)

📁 База данных: {db_size:.2f} МБ
🔍 Векторная БД: {vector_db_size:.2f} МБ
📅 Время работы: {await db.get_uptime()}
            """
            
            await message.answer(
                system_info,
                reply_markup=get_system_management_kb()
            )
        except Exception as e:
            await message.answer(
                f"❌ Ошибка при получении информации: {str(e)}",
                reply_markup=get_system_management_kb()
            )
    
    else:
        await message.answer(
            "Выберите действие из меню:",
            reply_markup=get_system_management_kb()
        )
