import random
import string
import html
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaDocument
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import (
    get_cancel_kb, get_admin_menu_kb, get_main_menu_kb,
    get_excel_export_kb, get_broadcast_type_kb, get_system_management_kb, get_back_to_menu_kb
)
from utils.excel_exporter import ExcelExporter
from utils.csv_exporter import CSVExporter
from utils.metrics_exporter import MetricsExporter
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
    collecting_photos = State()  # Новое состояние для сбора нескольких фото
    collecting_documents = State()  # Новое состояние для сбора документов
    confirming_media_group = State()  # Подтверждение перед отправкой

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
    selecting_container = State()  
    adding_photo = State()
    waiting_for_description = State()
    deleting_photo = State()
    
class GalleryManagementStates(StatesGroup):
    menu = State()
    adding_item = State()
    entering_title = State()
    uploading_photo = State()
    entering_description = State()
    viewing_items = State()
    deleting_item = State()

class BlanksManagementStates(StatesGroup):
    menu = State()
    adding_blank = State()
    entering_title = State()
    waiting_for_document = State()
    entering_description = State()
    viewing_blanks = State()
    deleting_blank = State()
    
def get_container_photos_kb():
    keyboard = [
        [KeyboardButton(text="📷 Добавить фото контейнера")],
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

@admin_router.message(SystemStates.in_system_menu, F.text == "🧪 Управление фото контейнеров")
async def manage_container_photos(message: Message, state: FSMContext):
    await message.answer(
        "🧪 Управление фото контейнеров\n\n"
        "Здесь вы можете добавлять и удалять фото пробирок.\n"
        "Фото автоматически показываются при выборе теста.",
        reply_markup=get_container_photos_kb()
    )
    await state.set_state(ContainerPhotoStates.menu)

@admin_router.message(ContainerPhotoStates.menu, F.text == "📷 Добавить фото контейнера")
async def start_add_photo(message: Message, state: FSMContext):
    loading_msg = await message.answer("⏳ Загружаю типы контейнеров...")
    
    try:
        # Получаем уникальные типы контейнеров (уже нормализованные)
        container_types = await db.get_unique_container_types()
        
        # Получаем все существующие фото
        all_photos = await db.get_all_container_photos()
        
        # Создаем словарь с нормализованными ключами
        photos_dict = {}
        for photo in all_photos:
            # Нормализуем тип контейнера из БД фото
            normalized_key = ' '.join(word.capitalize() for word in photo['container_type'].split())
            photos_dict[normalized_key] = photo
        
        await loading_msg.delete()
        
        if not container_types:
            await message.answer(
                "❌ Не найдено типов контейнеров в базе данных",
                reply_markup=get_container_photos_kb()
            )
            return
        
        # Создаем клавиатуру
        keyboard = []
        for container_type in container_types[:30]:  # Максимум 30 типов
            # container_type уже нормализован из get_unique_container_types
            has_photo = container_type in photos_dict
            
            # Формируем текст кнопки
            if len(container_type) > 40:
                button_text = container_type[:37] + "..."
            else:
                button_text = container_type
            
            # Добавляем индикатор
            if has_photo:
                button_text = f"✅ {button_text}"
            else:
                button_text = f"❌ {button_text}"
            
            keyboard.append([KeyboardButton(text=button_text)])
        
        keyboard.append([KeyboardButton(text="🔙 Отмена")])
        
        await state.update_data(container_types=container_types)
        
        # Статистика
        total_types = len(container_types)
        types_with_photos = len([ct for ct in container_types if ct in photos_dict])
        
        info_message = f"📦 <b>Выберите тип контейнера</b>\n\n"
        info_message += f"📊 <b>Статистика:</b>\n"
        info_message += f"• Всего типов: {total_types}\n"
        info_message += f"• С фото: {types_with_photos} ({types_with_photos/total_types*100:.0f}%)\n\n"
        info_message += "<b>Обозначения:</b>\n"
        info_message += "✅ - фото загружено\n"
        info_message += "❌ - фото отсутствует"
        
        await message.answer(
            info_message,
            reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True),
            parse_mode="HTML"
        )
        await state.set_state(ContainerPhotoStates.selecting_container)
        
    except Exception as e:
        print(f"[ERROR] in start_add_photo: {e}")
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=get_container_photos_kb()
        )

@admin_router.message(ContainerPhotoStates.selecting_container)
async def select_container_type(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, выберите тип контейнера из предложенного списка",
            reply_markup=get_container_photos_kb()
        )
        return
    
    if message.text == "🔙 Отмена":
        await message.answer(
            "📦 Управление фото контейнеров",
            reply_markup=get_container_photos_kb()
        )
        await state.set_state(ContainerPhotoStates.menu)
        return
    
    data = await state.get_data()
    container_types = data.get('container_types', [])
    
    # Убираем индикаторы
    search_text = message.text
    if search_text.startswith('✅ '):
        search_text = search_text[2:]
    elif search_text.startswith('❌ '):
        search_text = search_text[2:]
    
    # Убираем "..." если есть
    if search_text.endswith('...'):
        # Ищем полный тип который начинается с этого текста
        search_text = search_text[:-3]
        selected_type = None
        for container_type in container_types:
            if container_type.startswith(search_text):
                selected_type = container_type
                break
    else:
        # Точное совпадение
        selected_type = search_text if search_text in container_types else None
    
    if not selected_type:
        await message.answer(
            "❌ Тип контейнера не найден. Выберите из списка.",
            reply_markup=get_container_photos_kb()
        )
        await state.set_state(ContainerPhotoStates.menu)
        return
    
    await state.update_data(selected_type=selected_type)
    
    # Проверяем существующее фото (с нормализацией)
    existing_photo = await db.get_container_photo(selected_type)
    
    # Показываем информацию
    info_text = f"📦 <b>Выбран тип:</b>\n{html.escape(selected_type)}\n\n"
    
    if existing_photo:
        info_text += "✅ <b>Фото уже загружено!</b>\n"
        info_text += "Вы можете заменить его новым.\n\n"
    else:
        info_text += "❌ <b>Фото отсутствует</b>\n\n"
    
    info_text += "📸 <b>Отправьте фото этого контейнера:</b>"
    
    back_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True
    )
    
    # Если есть существующее фото, показываем его
    if existing_photo:
        try:
            caption = info_text
            if existing_photo.get('description'):
                caption += f"\n\n📝 <b>Текущее описание:</b> {html.escape(existing_photo['description'])}"
            
            await message.answer_photo(
                photo=existing_photo['file_id'],
                caption=caption,
                parse_mode="HTML",
                reply_markup=back_kb
            )
        except:
            await message.answer(
                info_text,
                reply_markup=back_kb,
                parse_mode="HTML"
            )
    else:
        await message.answer(
            info_text,
            reply_markup=back_kb,
            parse_mode="HTML"
        )
    
    await state.set_state(ContainerPhotoStates.adding_photo)

@admin_router.message(ContainerPhotoStates.adding_photo, F.photo)
async def receive_container_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]  # Берем лучшее качество
    file_id = photo.file_id
    
    await state.update_data(photo_file_id=file_id)
    
    await message.answer(
        "📝 Введите описание для контейнера\n"
        "(например: 'Пробирка с сиреневой крышкой / Калий ЭДТА')\n\n"
        "Или отправьте '-' чтобы пропустить:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(ContainerPhotoStates.waiting_for_description)
    
@admin_router.message(ContainerPhotoStates.adding_photo)
async def handle_non_photo(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        # Возвращаемся к выбору типа контейнера
        await start_add_photo(message, state)
        return
    await message.answer("❌ Пожалуйста, отправьте фото контейнера")

@admin_router.message(ContainerPhotoStates.waiting_for_description)
async def save_container_photo_with_description(message: Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await start_add_photo(message, state)
        return
    
    data = await state.get_data()
    selected_type = data.get('selected_type')
    file_id = data.get('photo_file_id')
    
    if not selected_type or not file_id:
        await message.answer(
            "❌ Ошибка: потеряны данные. Попробуйте заново.",
            reply_markup=get_container_photos_kb()
        )
        await state.set_state(ContainerPhotoStates.menu)
        return
    
    description = None if message.text == "-" else message.text
    
    # Сохраняем фото для типа контейнера
    success = await db.add_container_photo(
        container_type=selected_type,
        file_id=file_id,
        uploaded_by=message.from_user.id,
        description=description
    )
    
    if success:
        result_text = f"✅ <b>Фото успешно сохранено!</b>\n\n"
        result_text += f"📦 <b>Тип контейнера:</b> {html.escape(selected_type)}\n"
        if description:
            result_text += f"📝 <b>Описание:</b> {html.escape(description)}"
        
        await message.answer(
            result_text,
            parse_mode="HTML",
            reply_markup=get_container_photos_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении фото",
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
    
    # Показываем только краткую сводку, чтобы избежать "message is too long"
    text = "📈 Результаты опросов:\n\n"
    
    # Ограничиваем количество опросов и деталей
    for poll in polls[:5]:  # Показываем максимум 5 опросов
        text += f"📊 {poll['title']}\n"
        text += f"👥 Участников: {poll['total_responses']}\n"
        text += f"❓ Вопросов: {len(poll['questions'])}\n"
        
        # Показываем только первый вопрос как пример
        if poll['questions']:
            question = poll['questions'][0]
            q_text = question['text']
            if len(q_text) > 40:
                q_text = q_text[:37] + "..."
            text += f"📌 Пример: {q_text}\n"
            
            if question['type'] == 'rating':
                avg_rating = question.get('avg_rating', 0)
                text += f"   ⭐ Средняя оценка: {avg_rating:.1f}\n"
        
        text += "─" * 30 + "\n\n"
    
    if len(polls) > 5:
        text += f"...и еще {len(polls) - 5} опросов\n\n"
    
    text += "💡 Для детального просмотра используйте 'Выгрузить результаты'"
    
    await message.answer(text, reply_markup=get_poll_management_kb())

@admin_router.message(PollStates.poll_menu, F.text == "📥 Выгрузить результаты")
async def export_poll_results(message: Message, state: FSMContext):
    # Получаем список опросов с результатами
    polls_data = await db.get_full_poll_results()
    
    if not polls_data:
        await message.answer(
            "Нет опросов с результатами для выгрузки.",
            reply_markup=get_poll_management_kb()
        )
        return
    
    # Создаем клавиатуру с выбором опроса
    keyboard = []
    for poll in polls_data:
        button_text = f"📊 {poll['title']} ({poll['total_responses']} ответов)"
        if len(button_text) > 60:
            button_text = button_text[:57] + "..."
        keyboard.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"export_poll:{poll['id']}"
        )])
    
    # Добавляем кнопку "Все опросы"
    keyboard.append([InlineKeyboardButton(
        text="📥 Выгрузить все опросы",
        callback_data="export_poll:all"
    )])
    
    await message.answer(
        "📊 Выберите опрос для выгрузки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await state.set_state(PollStates.viewing_results)

@admin_router.callback_query(F.data.startswith("export_poll:"))
async def handle_poll_export(callback: CallbackQuery, state: FSMContext):
    poll_id_str = callback.data.split(":")[1]
    
    loading_msg = await callback.message.answer("⏳ Подготавливаю выгрузку...")
    
    try:
        # Получаем данные опроса(ов)
        if poll_id_str == "all":
            polls_data = await db.get_full_poll_results()
            caption = "📊 Результаты всех опросов"
        else:
            poll_id = int(poll_id_str)
            # Получаем данные конкретного опроса
            all_polls = await db.get_full_poll_results()
            polls_data = [p for p in all_polls if p['id'] == poll_id]
            
            if not polls_data:
                await loading_msg.delete()
                await callback.message.answer(
                    "❌ Опрос не найден.",
                    reply_markup=get_poll_management_kb()
                )
                await callback.answer()
                return
            
            caption = f"📊 Результаты опроса: {polls_data[0]['title']}"
        
        # Создаем Excel файл с результатами
        from utils.poll_exporter import PollExporter
        exporter = PollExporter()
        excel_data = await exporter.export_polls_to_excel(polls_data)
        
        filename = f"poll_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await loading_msg.delete()
        await callback.message.answer_document(
            BufferedInputFile(excel_data, filename),
            caption=f"{caption}\n📅 Дата выгрузки: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            reply_markup=get_poll_management_kb()
        )
        
        await callback.answer("✅ Выгрузка готова!")
        await state.clear()
        
    except Exception as e:
        await loading_msg.delete()
        await callback.message.answer(
            f"❌ Ошибка при выгрузке: {str(e)}",
            reply_markup=get_poll_management_kb()
        )
        await callback.answer()

@admin_router.message(PollStates.viewing_results, F.text == "🔙 Назад")
async def back_from_viewing_results(message: Message, state: FSMContext):
    await message.answer(
        "📋 Управление опросами",
        reply_markup=get_poll_management_kb()
    )
    await state.set_state(PollStates.poll_menu)

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
        [KeyboardButton(text="🖼️ Одно изображение")],
        [KeyboardButton(text="📸 Несколько изображений")],
        [KeyboardButton(text="📄 Документы")],
        [KeyboardButton(text="🎬 Видео")],
        [KeyboardButton(text="🎭 GIF")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_media_collection_kb():
    """Клавиатура для сбора множественных файлов"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="✅ Завершить сбор")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_caption_kb():
    """Клавиатура для подписи"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="➡️ Без подписи")],
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
            
        elif message.text == "💬 История общения с ботом":
            excel_data = await exporter.export_chat_history()
            filename = f"chat_history_{filename}"
            caption = "💬 История общения с ботом (вопросы и ответы)"
        
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
    
    elif message.text == "🖼️ Одно изображение":
        await state.update_data(content_type="photo")
        await message.answer(
            "📎 Отправьте изображение для рассылки:",
            reply_markup=get_back_to_menu_kb()
        )
        await state.set_state(BroadcastStates.waiting_for_media)
    
    elif message.text == "📸 Несколько изображений":
        await state.update_data(content_type="photo_group", media_group=[])
        await message.answer(
            "📸 Отправляйте изображения для рассылки (до 10 штук).\n\n"
            "После того как отправите все нужные изображения, "
            "нажмите 'Завершить сбор'",
            reply_markup=get_media_collection_kb()
        )
        await state.set_state(BroadcastStates.collecting_photos)
    
    elif message.text == "📄 Документы":
        await state.update_data(content_type="documents", media_group=[])
        await message.answer(
            "📄 Отправляйте документы для рассылки (до 10 штук).\n\n"
            "Поддерживаются форматы: PDF, DOC, DOCX, XLS, XLSX и др.\n\n"
            "После того как отправите все документы, "
            "нажмите 'Завершить сбор'",
            reply_markup=get_media_collection_kb()
        )
        await state.set_state(BroadcastStates.collecting_documents)
    
    elif message.text in ["🎬 Видео", "🎭 GIF"]:
        content_types = {
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
    
    caption = None if message.text in ["-", "➡️ Без подписи"] else message.text
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
    elif content_type == "photo_group":
        media_group = data.get('media_group', [])
        preview_text += f"Тип контента: Несколько изображений ({len(media_group)} шт.)\n"
        if data.get('caption'):
            preview_text += f"Подпись: {data.get('caption')}\n\n"
    elif content_type == "documents":
        media_group = data.get('media_group', [])
        preview_text += f"Тип контента: Документы ({len(media_group)} шт.)\n"
        if data.get('caption'):
            preview_text += f"Сообщение: {data.get('caption')}\n\n"
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
                final_text = f"📢 <b>Сообщение от группы техподдержки</b>\n\n{data.get('text')}"
                await bot.send_message(
                    recipient_id,
                    final_text,
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
            elif content_type == "photo_group":
                # Отправка группы изображений
                media_group = data.get('media_group', [])
                if media_group:
                    media_list = []
                    caption = f"📢 <b>Сообщение от группы техподдержки</b>\n\n{data.get('caption')}" if data.get('caption') else "📢 <b>Сообщение от группы техподдержки</b>"
                    
                    # Первое фото с подписью
                    media_list.append(InputMediaPhoto(
                        media=media_group[0]['file_id'],
                        caption=caption,
                        parse_mode="HTML"
                    ))
                    
                    # Остальные фото без подписи
                    for item in media_group[1:]:
                        media_list.append(InputMediaPhoto(media=item['file_id']))
                    
                    await bot.send_media_group(recipient_id, media=media_list)
            elif content_type == "documents":
                # Отправка документов
                media_group = data.get('media_group', [])
                caption_text = f"📢 <b>Сообщение от группы техподдержки</b>\n\n{data.get('caption')}" if data.get('caption') else "📢 <b>Сообщение от группы техподдержки</b>"
                
                # Отправляем сначала сообщение, если есть
                if data.get('caption'):
                    await bot.send_message(
                        recipient_id,
                        caption_text,
                        parse_mode="HTML"
                    )
                
                # Затем отправляем каждый документ по отдельности
                for doc in media_group:
                    await bot.send_document(
                        recipient_id,
                        document=doc['file_id']
                    )
                    await asyncio.sleep(0.05)  # Маленькая задержка между документами
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

# Обработчики для сбора множественных изображений
@admin_router.message(BroadcastStates.collecting_photos, F.photo)
async def collect_photo(message: Message, state: FSMContext):
    """Сбор изображений в группу"""
    data = await state.get_data()
    media_group = data.get('media_group', [])
    
    # Ограничение в 10 фото
    if len(media_group) >= 10:
        await message.answer(
            "❌ Достигнут лимит в 10 изображений.\n"
            "Нажмите 'Завершить сбор' для продолжения.",
            reply_markup=get_media_collection_kb()
        )
        return
    
    photo = message.photo[-1]
    media_group.append({
        'type': 'photo',
        'file_id': photo.file_id
    })
    
    await state.update_data(media_group=media_group)
    await message.answer(
        f"✅ Изображение {len(media_group)} добавлено!\n\n"
        f"Можете отправить еще (максимум {10 - len(media_group)}) "
        f"или нажмите 'Завершить сбор'",
        reply_markup=get_media_collection_kb()
    )

@admin_router.message(BroadcastStates.collecting_photos, F.text == "✅ Завершить сбор")
async def finish_collecting_photos(message: Message, state: FSMContext):
    """Завершение сбора изображений"""
    data = await state.get_data()
    media_group = data.get('media_group', [])
    
    if not media_group:
        await message.answer(
            "❌ Вы не отправили ни одного изображения!\n"
            "Отправьте хотя бы одно изображение.",
            reply_markup=get_media_collection_kb()
        )
        return
    
    await message.answer(
        f"📝 Введите общую подпись для {len(media_group)} изображений:\n\n"
        "Поддерживается HTML-форматирование.\n"
        "Или нажмите 'Без подписи'",
        reply_markup=get_caption_kb()
    )
    await state.set_state(BroadcastStates.waiting_for_caption)

@admin_router.message(BroadcastStates.collecting_photos)
async def invalid_photo_input(message: Message, state: FSMContext):
    """Обработка неверного ввода при сборе фото"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    await message.answer(
        "❌ Пожалуйста, отправьте изображение или нажмите 'Завершить сбор'",
        reply_markup=get_media_collection_kb()
    )

# Обработчики для сбора документов
@admin_router.message(BroadcastStates.collecting_documents, F.document)
async def collect_document(message: Message, state: FSMContext):
    """Сбор документов в группу"""
    data = await state.get_data()
    media_group = data.get('media_group', [])
    
    # Ограничение в 10 документов
    if len(media_group) >= 10:
        await message.answer(
            "❌ Достигнут лимит в 10 документов.\n"
            "Нажмите 'Завершить сбор' для продолжения.",
            reply_markup=get_media_collection_kb()
        )
        return
    
    document = message.document
    media_group.append({
        'type': 'document',
        'file_id': document.file_id,
        'file_name': document.file_name
    })
    
    await state.update_data(media_group=media_group)
    await message.answer(
        f"✅ Документ {len(media_group)} '{document.file_name}' добавлен!\n\n"
        f"Можете отправить еще (максимум {10 - len(media_group)}) "
        f"или нажмите 'Завершить сбор'",
        reply_markup=get_media_collection_kb()
    )

@admin_router.message(BroadcastStates.collecting_documents, F.text == "✅ Завершить сбор")
async def finish_collecting_documents(message: Message, state: FSMContext):
    """Завершение сбора документов"""
    data = await state.get_data()
    media_group = data.get('media_group', [])
    
    if not media_group:
        await message.answer(
            "❌ Вы не отправили ни одного документа!\n"
            "Отправьте хотя бы один документ.",
            reply_markup=get_media_collection_kb()
        )
        return
    
    await message.answer(
        f"📝 Введите общее сообщение для {len(media_group)} документов:\n\n"
        "Поддерживается HTML-форматирование.\n"
        "Или нажмите 'Без подписи'",
        reply_markup=get_caption_kb()
    )
    await state.set_state(BroadcastStates.waiting_for_caption)

@admin_router.message(BroadcastStates.collecting_documents)
async def invalid_document_input(message: Message, state: FSMContext):
    """Обработка неверного ввода при сборе документов"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    await message.answer(
        "❌ Пожалуйста, отправьте документ или нажмите 'Завершить сбор'",
        reply_markup=get_media_collection_kb()
    )

@admin_router.message(F.text == " Пользователи")
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
        
def get_content_management_kb():
    """Клавиатура управления контентом"""
    keyboard = [
        [KeyboardButton(text="⚙️ Управление галереей")],  # ← Изменено
        [KeyboardButton(text="⚙️ Управление бланками")],  # ← Изменено
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_gallery_management_kb():
    """Клавиатура управления галереей"""
    keyboard = [
        [KeyboardButton(text="➕ Добавить в галерею")],
        [KeyboardButton(text="📋 Просмотр галереи")],
        [KeyboardButton(text="🗑️ Удалить из галереи")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_blanks_management_kb():
    """Клавиатура управления бланками"""
    keyboard = [
        [KeyboardButton(text="➕ Добавить бланк")],
        [KeyboardButton(text="📋 Просмотр бланков")],
        [KeyboardButton(text="🗑️ Удалить бланк")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# Обработчики для управления контентом
@admin_router.message(F.text == "🎨 Управление контентом")
async def content_management(message: Message, state: FSMContext):
    """Главное меню управления контентом"""
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    await message.answer(
        "🎨 Управление контентом\n\n"
        "Здесь вы можете управлять:\n"
        "• Галереей пробирок и контейнеров\n"
        "• Ссылками на бланки",
        reply_markup=get_content_management_kb()
    )

# Обработчики для галереи
@admin_router.message(F.text == "⚙️ Управление галереей")
async def gallery_management(message: Message, state: FSMContext):
    """Управление галереей пробирок"""
    await message.answer(
        "🖼️ Управление галереей пробирок\n\n"
        "Добавляйте фотографии пробирок и контейнеров, "
        "которые будут доступны пользователям.",
        reply_markup=get_gallery_management_kb()
    )
    await state.set_state(GalleryManagementStates.menu)

@admin_router.message(GalleryManagementStates.menu, F.text == "➕ Добавить в галерею")
async def start_add_gallery_item(message: Message, state: FSMContext):
    """Начало добавления элемента в галерею"""
    await message.answer(
        "📝 Введите название для элемента галереи:\n"
        "(например: 'Пробирка с ЭДТА' или 'Контейнер для мочи')",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(GalleryManagementStates.entering_title)

@admin_router.message(GalleryManagementStates.entering_title)
async def gallery_enter_title(message: Message, state: FSMContext):
    """Ввод названия элемента галереи"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_gallery_management_kb())
        return
    
    await state.update_data(gallery_title=message.text)
    await message.answer(
        "📸 Теперь отправьте фотографию для этого элемента:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(GalleryManagementStates.uploading_photo)

@admin_router.message(GalleryManagementStates.uploading_photo, F.photo)
async def gallery_upload_photo(message: Message, state: FSMContext):
    """Загрузка фото для галереи"""
    photo = message.photo[-1]  # Берем лучшее качество
    file_id = photo.file_id
    
    await state.update_data(gallery_photo_id=file_id)
    await message.answer(
        "📝 Введите описание для этого элемента:\n"
        "(можно указать особенности, объем, цвет крышки и т.д.)\n\n"
        "Или отправьте '-' чтобы пропустить:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(GalleryManagementStates.entering_description)

@admin_router.message(GalleryManagementStates.uploading_photo)
async def gallery_invalid_photo(message: Message, state: FSMContext):
    """Обработка не-фото в состоянии загрузки"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_gallery_management_kb())
        return
    await message.answer("❌ Пожалуйста, отправьте фотографию")

@admin_router.message(GalleryManagementStates.entering_description)
async def gallery_save_item(message: Message, state: FSMContext):
    """Сохранение элемента галереи"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_gallery_management_kb())
        return
    
    data = await state.get_data()
    title = data.get('gallery_title')
    file_id = data.get('gallery_photo_id')
    description = None if message.text == "-" else message.text
    
    # Сохраняем в БД
    success = await db.add_gallery_item(
        title=title,
        file_id=file_id,
        description=description,
        added_by=message.from_user.id
    )
    
    if success:
        await message.answer(
            f"✅ Элемент успешно добавлен в галерею!\n\n"
            f"📌 Название: {html.escape(title)}\n"
            f"📝 Описание: {html.escape(description) if description else 'Не указано'}",
            parse_mode="HTML",
            reply_markup=get_gallery_management_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении элемента",
            reply_markup=get_gallery_management_kb()
        )
    
    await state.set_state(GalleryManagementStates.menu)

@admin_router.message(GalleryManagementStates.menu, F.text == "📋 Просмотр галереи")
async def view_gallery_items(message: Message):
    """Просмотр всех элементов галереи"""
    items = await db.get_all_gallery_items()
    
    if not items:
        await message.answer(
            "Галерея пока пуста.",
            reply_markup=get_gallery_management_kb()
        )
        return
    
    text = "📋 Элементы галереи:\n\n"
    for i, item in enumerate(items, 1):
        text += f"{i}. {item['title']}\n"
        if item.get('description'):
            text += f"   📝 {item['description'][:50]}{'...' if len(item['description']) > 50 else ''}\n"
        text += f"   📅 Добавлено: {item['created_at']}\n\n"
    
    await message.answer(text, reply_markup=get_gallery_management_kb())

@admin_router.message(GalleryManagementStates.menu, F.text == "🗑️ Удалить из галереи")
async def start_delete_gallery_item(message: Message, state: FSMContext):
    """Начало удаления элемента из галереи"""
    items = await db.get_all_gallery_items()
    
    if not items:
        await message.answer(
            "Галерея пуста.",
            reply_markup=get_gallery_management_kb()
        )
        return
    
    keyboard = []
    for item in items[:20]:  # Максимум 20 элементов
        keyboard.append([
            KeyboardButton(text=f"❌ {item['title'][:40]}")
        ])
    keyboard.append([KeyboardButton(text="🔙 Отмена")])
    
    await message.answer(
        "Выберите элемент для удаления:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )
    await state.set_state(GalleryManagementStates.deleting_item)

@admin_router.message(GalleryManagementStates.deleting_item)
async def delete_gallery_item(message: Message, state: FSMContext):
    """Удаление элемента из галереи"""
    if message.text == "🔙 Отмена":
        await message.answer(
            "Операция отменена.",
            reply_markup=get_gallery_management_kb()
        )
        await state.set_state(GalleryManagementStates.menu)
        return
    
    if message.text.startswith("❌ "):
        title = message.text[2:]
        items = await db.get_all_gallery_items()
        
        for item in items:
            if item['title'].startswith(title):
                success = await db.delete_gallery_item(item['id'])
                if success:
                    await message.answer(
                        f"✅ Элемент '{item['title']}' удален из галереи",
                        reply_markup=get_gallery_management_kb()
                    )
                else:
                    await message.answer(
                        "❌ Ошибка при удалении",
                        reply_markup=get_gallery_management_kb()
                    )
                break
    
    await state.set_state(GalleryManagementStates.menu)

# Обработчики для бланков
@admin_router.message(F.text == "⚙️ Управление бланками")
async def blanks_management(message: Message, state: FSMContext):
    """Управление документами бланков"""
    await message.answer(
        "📄 Управление бланками\n\n"
        "Добавляйте документы бланков, "
        "которые будут доступны пользователям прямо в телеграм.",
        reply_markup=get_blanks_management_kb()
    )
    await state.set_state(BlanksManagementStates.menu)

@admin_router.message(BlanksManagementStates.menu, F.text == "➕ Добавить бланк")
async def start_add_blank(message: Message, state: FSMContext):
    """Начало добавления бланка"""
    await message.answer(
        "📝 Введите название бланка:\n"
        "(например: 'Направление на анализ крови' или 'Бланк результатов')",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(BlanksManagementStates.entering_title)

@admin_router.message(BlanksManagementStates.entering_title)
async def blank_enter_title(message: Message, state: FSMContext):
    """Ввод названия бланка"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_blanks_management_kb())
        return
    
    await state.update_data(blank_title=message.text)
    await message.answer(
        "📎 Теперь отправьте документ (PDF, DOC, DOCX, XLS, XLSX и др.):\n\n"
        "Документ будет сохранен и доступен пользователям прямо в телеграм",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(BlanksManagementStates.waiting_for_document)

@admin_router.message(BlanksManagementStates.waiting_for_document, F.document)
async def blank_receive_document(message: Message, state: FSMContext):
    """Получение документа бланка"""
    document = message.document
    file_id = document.file_id
    
    # Сохраняем file_id и информацию о файле
    await state.update_data(
        blank_file_id=file_id,
        blank_file_name=document.file_name,
        blank_file_size=document.file_size
    )
    
    await message.answer(
        "📝 Введите описание для бланка:\n"
        "(краткое описание, для чего используется)\n\n"
        "Или отправьте '-' чтобы пропустить:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(BlanksManagementStates.entering_description)

@admin_router.message(BlanksManagementStates.waiting_for_document)
async def blank_invalid_document(message: Message, state: FSMContext):
    """Обработка не-документа в состоянии загрузки"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_blanks_management_kb())
        return
    await message.answer("❌ Пожалуйста, отправьте документ (файл)")

@admin_router.message(BlanksManagementStates.entering_description)
async def blank_save_item(message: Message, state: FSMContext):
    """Сохранение бланка"""
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_blanks_management_kb())
        return
    
    data = await state.get_data()
    title = data.get('blank_title')
    file_id = data.get('blank_file_id')
    file_name = data.get('blank_file_name', 'документ')
    description = None if message.text == "-" else message.text
    
    if not title or not file_id:
        await message.answer(
            "❌ Ошибка: потеряны данные. Попробуйте заново.",
            reply_markup=get_blanks_management_kb()
        )
        await state.set_state(BlanksManagementStates.menu)
        return
    
    # Сохраняем в БД
    success = await db.add_blank_document(
        title=title,
        file_id=file_id,
        description=description,
        added_by=message.from_user.id
    )
    
    if success:
        await message.answer(
            f"✅ Бланк успешно добавлен!\n\n"
            f"📌 Название: {html.escape(title)}\n"
            f"📎 Файл: {html.escape(file_name)}\n"
            f"📝 Описание: {html.escape(description) if description else 'Не указано'}",
            parse_mode="HTML",
            reply_markup=get_blanks_management_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении бланка",
            reply_markup=get_blanks_management_kb()
        )
    
    await state.set_state(BlanksManagementStates.menu)

@admin_router.message(BlanksManagementStates.menu, F.text == "📋 Просмотр бланков")
async def view_blank_items(message: Message):
    """Просмотр всех бланков"""
    items = await db.get_all_blank_documents()
    
    if not items:
        await message.answer(
            "Список бланков пока пуст.",
            reply_markup=get_blanks_management_kb()
        )
        return
    
    text = "📋 Список бланков:\n\n"
    for i, item in enumerate(items, 1):
        text += f"{i}. {item['title']}\n"
        text += f"   📎 Документ загружен\n"
        if item.get('description'):
            text += f"   📝 {item['description'][:50]}{'...' if len(item['description']) > 50 else ''}\n"
        text += f"   📅 Добавлено: {item['created_at']}\n\n"
    
    await message.answer(text, reply_markup=get_blanks_management_kb())

@admin_router.message(BlanksManagementStates.menu, F.text == "🗑️ Удалить бланк")
async def start_delete_blank(message: Message, state: FSMContext):
    """Начало удаления бланка"""
    items = await db.get_all_blank_documents()
    
    if not items:
        await message.answer(
            "Список бланков пуст.",
            reply_markup=get_blanks_management_kb()
        )
        return
    
    keyboard = []
    for item in items[:20]:
        keyboard.append([
            KeyboardButton(text=f"❌ {item['title'][:40]}")
        ])
    keyboard.append([KeyboardButton(text="🔙 Отмена")])
    
    await message.answer(
        "Выберите бланк для удаления:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )
    await state.set_state(BlanksManagementStates.deleting_blank)

@admin_router.message(BlanksManagementStates.deleting_blank)
async def delete_blank(message: Message, state: FSMContext):
    """Удаление бланка"""
    if message.text == "🔙 Отмена":
        await message.answer(
            "Операция отменена.",
            reply_markup=get_blanks_management_kb()
        )
        await state.set_state(BlanksManagementStates.menu)
        return
    
    if message.text.startswith("❌ "):
        title = message.text[2:]
        items = await db.get_all_blank_documents()
        
        for item in items:
            if item['title'].startswith(title):
                success = await db.delete_blank_document(item['id'])
                if success:
                    await message.answer(
                        f"✅ Бланк '{item['title']}' удален",
                        reply_markup=get_blanks_management_kb()
                    )
                else:
                    await message.answer(
                        "❌ Ошибка при удалении",
                        reply_markup=get_blanks_management_kb()
                    )
                break
    
    await state.set_state(BlanksManagementStates.menu)

# Обработчики возврата в меню
@admin_router.message(GalleryManagementStates.menu, F.text == "🔙 Назад")
async def back_from_gallery(message: Message, state: FSMContext):
    await state.clear()
    await content_management(message, state)

@admin_router.message(BlanksManagementStates.menu, F.text == "🔙 Назад")
async def back_from_blanks(message: Message, state: FSMContext):
    await state.clear()
    await content_management(message, state)

@admin_router.message(F.text == "📈 Экспорт метрик")
async def export_metrics(message: Message):
    """Экспорт метрик в Excel"""
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    loading_msg = await message.answer("⏳ Формирую отчет по метрикам...")
    
    try:
        # Обновляем все метрики перед экспортом
        await db.update_daily_metrics()
        await db.update_quality_metrics()
        await db.update_system_metrics()
        
        exporter = MetricsExporter(db)
        excel_data = await exporter.export_comprehensive_metrics(days=30)
        
        filename = f"metrics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await loading_msg.delete()
        await message.answer_document(
            BufferedInputFile(excel_data, filename),
            caption=(
                "📊 <b>Полный отчет по метрикам системы</b>\n\n"
                "Включает:\n"
                "• Клиентские метрики (DAU, retention, сессии)\n"
                "• Технические метрики (производительность, ресурсы)\n"
                "• Метрики качества (успешность, типы запросов)\n"
                "• Детальные данные по запросам\n\n"
                f"📅 Период: последние 30 дней\n"
                f"🕐 Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            ),
            parse_mode="HTML",
            reply_markup=get_admin_menu_kb()
        )
        
    except Exception as e:
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при экспорте метрик: {str(e)}",
            reply_markup=get_admin_menu_kb()
        )

@admin_router.message(F.text == "📃 Отчет")
async def export_session_activity_report(message: Message):
    """Экспорт детального отчета по времени активности пользователей"""
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    loading_msg = await message.answer(
        "⏳ Формирую детальный отчет по времени активности...\n\n"
        "Это может занять некоторое время, так как анализируются:\n"
        "• Все сессии пользователей\n"
        "• Паузы между запросами\n"
        "• Причины длительных сессий\n"
        "• Рекомендации по оптимизации"
    )
    
    try:
        # Обновляем метрики сессий
        await db.close_inactive_sessions()
        
        exporter = MetricsExporter(db)
        excel_data = await exporter.export_session_activity_report(days=30)
        
        filename = f"session_activity_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await loading_msg.delete()
        await message.answer_document(
            BufferedInputFile(excel_data, filename),
            caption=(
                "📃 <b>Детальный отчет по времени активности</b>\n\n"
                "📊 <b>Что включено:</b>\n"
                "• <b>Сводка</b> - общая статистика по всем сессиям\n"
                "• <b>Детали сессий</b> - полная информация по каждой сессии\n"
                "• <b>Анализ проблем</b> - разбор запредельных сессий (>30 мин)\n"
                "• <b>Рекомендации</b> - советы по оптимизации\n\n"
                "🔍 <b>Анализ включает:</b>\n"
                "• Причины длительных сессий\n"
                "• Паузы между запросами\n"
                "• Время на изучение материала\n"
                "• Проблемные сессии с рекомендациями\n\n"
                f"📅 Период анализа: последние 30 дней\n"
                f"🕐 Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            ),
            parse_mode="HTML",
            reply_markup=get_admin_menu_kb()
        )
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[ERROR] Session activity report failed: {error_detail}")
        
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при формировании отчета:\n{str(e)}\n\n"
            "Возможные причины:\n"
            "• Недостаточно данных о сессиях\n"
            "• Проблемы с базой данных\n"
            "• Ошибка при создании Excel файла",
            reply_markup=get_admin_menu_kb()
        )
