"""
Обработчики для стоп-листа
"""
import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database.db_init import db
from bot.keyboards import (
    CURRENT_STOPLIST_BUTTON_ALIASES,
    get_admin_menu_kb,
    get_main_menu_kb,
    get_menu_by_role,
)

news_router = Router()

# ============================================================
# STATES
# ============================================================

class StoplistStates(StatesGroup):
    """Состояния для управления стоп-листом (админ)"""
    menu = State()
    uploading_suspended = State()
    uploading_removed = State()
    uploading_instruction_stoplist = State()
    uploading_instruction_blanks = State()

# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def get_stoplist_management_kb():
    """Клавиатура управления стоп-листом для админа"""
    keyboard = [
        [KeyboardButton(text="📤 Загрузить 'Тесты в приостановке'")],
        [KeyboardButton(text="📤 Загрузить 'Тесты выведенные'")],
        [KeyboardButton(text="🎥 Видео-инструкция: стоп-лист")],
        [KeyboardButton(text="🎥 Видео-инструкция: бланки")],
        [KeyboardButton(text="📋 Текущие файлы")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def _extract_media_file_id_and_type(message: Message) -> tuple[str | None, str | None]:
    """Достает file_id и тип медиа из входящего сообщения (видео/GIF)."""
    # Видео
    if message.video:
        return message.video.file_id, 'video'

    # GIF (animation)
    if message.animation:
        return message.animation.file_id, 'animation'

    # Иногда GIF прилетает как документ
    if message.document and message.document.mime_type:
        mime = message.document.mime_type.lower()
        if 'gif' in mime:
            return message.document.file_id, 'animation'

    return None, None

def create_stoplist_keyboard():
    """Создает inline клавиатуру для стоп-листа"""
    keyboard = [
        [InlineKeyboardButton(
            text="⏸️ Тесты в приостановке",
            callback_data="stoplist_suspended"
        )],
        [InlineKeyboardButton(
            text="❌ Тесты выведенные",
            callback_data="stoplist_removed"
        )],
        [InlineKeyboardButton(
            text="🔙 Закрыть",
            callback_data="close_stoplist"
        )]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============================================================
# ОБРАБОТЧИКИ ДЛЯ АДМИНА
# ============================================================

@news_router.message(F.text == "⚙️ Управление стоп-листом")
async def stoplist_management(message: Message, state: FSMContext):
    """Управление стоп-листом (только для админа)"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    await message.answer(
        "⚙️ <b>Управление стоп-листом</b>\n\n"
        "Здесь вы можете обновить файлы стоп-листа:\n"
        "• ⏸️ Тесты в приостановке\n"
        "• ❌ Тесты выведенные\n\n"
        "Поддерживаются все типы файлов.",
        parse_mode="HTML",
        reply_markup=get_stoplist_management_kb()
    )
    await state.set_state(StoplistStates.menu)

@news_router.message(StoplistStates.menu, F.text == "📤 Загрузить 'Тесты в приостановке'")
async def upload_suspended_tests(message: Message, state: FSMContext):
    """Начало загрузки файла для тестов в приостановке"""
    await message.answer(
        "📤 <b>Загрузка файла 'Тесты в приостановке'</b>\n\n"
        "Отправьте файл со списком тестов, которые временно недоступны для заказа.\n\n"
        "Поддерживаются все форматы: PDF, DOC, XLS, изображения и т.д.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(StoplistStates.uploading_suspended)

@news_router.message(StoplistStates.menu, F.text == "📤 Загрузить 'Тесты выведенные'")
async def upload_removed_tests(message: Message, state: FSMContext):
    """Начало загрузки файла для выведенных тестов"""
    await message.answer(
        "📤 <b>Загрузка файла 'Тесты выведенные'</b>\n\n"
        "Отправьте файл со списком тестов, полностью выведенных из ассортимента.\n\n"
        "Поддерживаются все форматы: PDF, DOC, XLS, изображения и т.д.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(StoplistStates.uploading_removed)


@news_router.message(StoplistStates.menu, F.text == "🎥 Видео-инструкция: стоп-лист")
async def upload_stoplist_instruction_video(message: Message, state: FSMContext):
    """Загрузка видео-инструкции для стоп-листа (админ)."""
    await message.answer(
        "🎥 <b>Видео-инструкция: стоп-лист</b>\n\n"
        "Отправьте видео (MP4) или GIF.\n"
        "После загрузки бот будет показывать это видео, когда пользователь спрашивает про стоп-лист.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(StoplistStates.uploading_instruction_stoplist)


@news_router.message(StoplistStates.menu, F.text == "🎥 Видео-инструкция: бланки")
async def upload_blanks_instruction_video(message: Message, state: FSMContext):
    """Загрузка видео-инструкции для бланков (админ)."""
    await message.answer(
        "🎥 <b>Видео-инструкция: бланки</b>\n\n"
        "Отправьте видео (MP4) или GIF.\n"
        "После загрузки бот будет показывать это видео, когда пользователь спрашивает про бланки/формы.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(StoplistStates.uploading_instruction_blanks)

@news_router.message(StoplistStates.uploading_suspended, F.document | F.photo | F.video)
async def save_suspended_file(message: Message, state: FSMContext):
    """Сохранение файла для тестов в приостановке"""
    # Определяем file_id в зависимости от типа
    if message.document:
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    elif message.video:
        file_id = message.video.file_id
    else:
        await message.answer("❌ Неподдерживаемый тип файла")
        return
    
    success = await db.update_stoplist_file('suspended', file_id)
    
    if success:
        await message.answer(
            "✅ Файл 'Тесты в приостановке' успешно обновлен!",
            reply_markup=get_stoplist_management_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении файла",
            reply_markup=get_stoplist_management_kb()
        )
    
    await state.set_state(StoplistStates.menu)

@news_router.message(StoplistStates.uploading_removed, F.document | F.photo | F.video)
async def save_removed_file(message: Message, state: FSMContext):
    """Сохранение файла для выведенных тестов"""
    # Определяем file_id в зависимости от типа
    if message.document:
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    elif message.video:
        file_id = message.video.file_id
    else:
        await message.answer("❌ Неподдерживаемый тип файла")
        return
    
    success = await db.update_stoplist_file('removed', file_id)
    
    if success:
        await message.answer(
            "✅ Файл 'Тесты выведенные' успешно обновлен!",
            reply_markup=get_stoplist_management_kb()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении файла",
            reply_markup=get_stoplist_management_kb()
        )
    
    await state.set_state(StoplistStates.menu)


@news_router.message(StoplistStates.uploading_instruction_stoplist)
async def save_stoplist_instruction_media(message: Message, state: FSMContext):
    """Сохраняет медиа-инструкцию для стоп-листа (video/gif)."""
    if message.text == "🔙 Отмена":
        await message.answer(
            "Операция отменена.",
            reply_markup=get_stoplist_management_kb(),
        )
        await state.set_state(StoplistStates.menu)
        return

    file_id, media_type = _extract_media_file_id_and_type(message)
    if not file_id or not media_type:
        await message.answer("❌ Пожалуйста, отправьте видео (MP4) или GIF.")
        return

    success = await db.set_instruction_media(
        media_key="instruction_stoplist",
        file_id=file_id,
        media_type=media_type,
    )

    if success:
        await message.answer(
            "✅ Видео-инструкция для стоп-листа сохранена!",
            reply_markup=get_stoplist_management_kb(),
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении видео-инструкции.",
            reply_markup=get_stoplist_management_kb(),
        )

    await state.set_state(StoplistStates.menu)


@news_router.message(StoplistStates.uploading_instruction_blanks)
async def save_blanks_instruction_media(message: Message, state: FSMContext):
    """Сохраняет медиа-инструкцию для бланков (video/gif)."""
    if message.text == "🔙 Отмена":
        await message.answer(
            "Операция отменена.",
            reply_markup=get_stoplist_management_kb(),
        )
        await state.set_state(StoplistStates.menu)
        return

    file_id, media_type = _extract_media_file_id_and_type(message)
    if not file_id or not media_type:
        await message.answer("❌ Пожалуйста, отправьте видео (MP4) или GIF.")
        return

    success = await db.set_instruction_media(
        media_key="instruction_blanks",
        file_id=file_id,
        media_type=media_type,
    )

    if success:
        await message.answer(
            "✅ Видео-инструкция для бланков сохранена!",
            reply_markup=get_stoplist_management_kb(),
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении видео-инструкции.",
            reply_markup=get_stoplist_management_kb(),
        )

    await state.set_state(StoplistStates.menu)

@news_router.message(StoplistStates.uploading_suspended)
async def handle_invalid_file_suspended(message: Message, state: FSMContext):
    """Обработка отмены или неверного формата для suspended"""
    if message.text == "🔙 Отмена":
        await message.answer(
            "Операция отменена.",
            reply_markup=get_stoplist_management_kb()
        )
        await state.set_state(StoplistStates.menu)
    else:
        await message.answer(
            "❌ Пожалуйста, отправьте файл (документ, фото или видео)"
        )

@news_router.message(StoplistStates.uploading_removed)
async def handle_invalid_file_removed(message: Message, state: FSMContext):
    """Обработка отмены или неверного формата для removed"""
    if message.text == "🔙 Отмена":
        await message.answer(
            "Операция отменена.",
            reply_markup=get_stoplist_management_kb()
        )
        await state.set_state(StoplistStates.menu)
    else:
        await message.answer(
            "❌ Пожалуйста, отправьте файл (документ, фото или видео)"
        )

@news_router.message(StoplistStates.menu, F.text == "📋 Текущие файлы")
async def show_current_stoplist_files(message: Message):
    """Показывает информацию о текущих файлах стоп-листа"""
    suspended_file = await db.get_stoplist_file('suspended')
    removed_file = await db.get_stoplist_file('removed')
    
    text = "📋 <b>Текущие файлы стоп-листа:</b>\n\n"
    
    text += "⏸️ <b>Тесты в приостановке:</b>\n"
    text += "   " + ("✅ Загружен" if suspended_file else "❌ Не загружен") + "\n\n"
    
    text += "❌ <b>Тесты выведенные:</b>\n"
    text += "   " + ("✅ Загружен" if removed_file else "❌ Не загружен")

    # Видео-инструкции
    stoplist_instruction = await db.get_instruction_media('instruction_stoplist')
    blanks_instruction = await db.get_instruction_media('instruction_blanks')

    text += "\n\n🎥 <b>Видео-инструкции:</b>\n"
    text += "• Стоп-лист: " + ("✅ Загружено" if stoplist_instruction else "❌ Не загружено") + "\n"
    text += "• Бланки: " + ("✅ Загружено" if blanks_instruction else "❌ Не загружено")
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_stoplist_management_kb()
    )

@news_router.message(StoplistStates.menu, F.text == "🔙 Назад")
async def back_from_stoplist_management(message: Message, state: FSMContext):
    """Возврат из управления стоп-листом"""
    await state.clear()
    await message.answer(
        "Главное меню администратора",
        reply_markup=get_admin_menu_kb()
    )

# ============================================================
# ОБРАБОТЧИКИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

@news_router.message(F.text.in_(CURRENT_STOPLIST_BUTTON_ALIASES))
async def show_stoplist(message: Message):
    """Показ стоп-листа пользователю (и админу в режиме просмотра)"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return
    
    # Проверяем наличие файлов
    suspended_file = await db.get_stoplist_file('suspended')
    removed_file = await db.get_stoplist_file('removed')
    
    if not suspended_file and not removed_file:
        await message.answer(
            "📋 <b>Актуальный стоп-лист</b>\n\n"
            "Файлы стоп-листа пока не загружены.\n"
            "Обратитесь к администратору.",
            parse_mode="HTML",
            reply_markup=get_menu_by_role(user.get('role', 'user'))
        )
        return
    
    await message.answer(
        "📋 <b>Актуальный стоп-лист</b>\n\n"
        "Выберите нужный файл:",
        parse_mode="HTML",
        reply_markup=create_stoplist_keyboard()
    )

@news_router.callback_query(F.data == "stoplist_suspended")
async def send_suspended_file(callback: CallbackQuery):
    """Отправка файла с тестами в приостановке"""
    await callback.answer()
    
    file_id = await db.get_stoplist_file('suspended')
    
    if not file_id:
        await callback.answer("❌ Файл не загружен", show_alert=True)
        return
    
    try:
        # Удаляем список
        await callback.message.delete()
    except:
        pass
    
    # Отправляем файл
    from bot.handlers import bot
    
    caption = (
        "⏸️ <b>Тесты в приостановке</b>\n\n"
        "Список тестов, временно недоступных для заказа"
    )
    
    back_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="back_to_stoplist")],
            [InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_stoplist")]
        ]
    )
    
    try:
        await bot.send_document(
            callback.message.chat.id,
            document=file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=back_keyboard
        )
    except Exception as e:
        print(f"[ERROR] Failed to send suspended file: {e}")
        await callback.message.answer(
            "❌ Не удалось отправить файл. Возможно, он был удален.",
            reply_markup=back_keyboard
        )

@news_router.callback_query(F.data == "stoplist_removed")
async def send_removed_file(callback: CallbackQuery):
    """Отправка файла с выведенными тестами"""
    await callback.answer()
    
    file_id = await db.get_stoplist_file('removed')
    
    if not file_id:
        await callback.answer("❌ Файл не загружен", show_alert=True)
        return
    
    try:
        # Удаляем список
        await callback.message.delete()
    except:
        pass
    
    # Отправляем файл
    from bot.handlers import bot
    
    caption = (
        "❌ <b>Тесты выведенные</b>\n\n"
        "Список тестов, полностью выведенных из ассортимента"
    )
    
    back_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="back_to_stoplist")],
            [InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_stoplist")]
        ]
    )
    
    try:
        await bot.send_document(
            callback.message.chat.id,
            document=file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=back_keyboard
        )
    except Exception as e:
        print(f"[ERROR] Failed to send removed file: {e}")
        await callback.message.answer(
            "❌ Не удалось отправить файл. Возможно, он был удален.",
            reply_markup=back_keyboard
        )

@news_router.callback_query(F.data == "back_to_stoplist")
async def back_to_stoplist(callback: CallbackQuery):
    """Возврат к списку стоп-листа"""
    await callback.answer()
    
    try:
        # Удаляем файл
        await callback.message.delete()
        
        # Показываем список снова
        await callback.message.answer(
            "📋 <b>Актуальный стоп-лист</b>\n\n"
            "Выберите нужный файл:",
            parse_mode="HTML",
            reply_markup=create_stoplist_keyboard()
        )
    except Exception as e:
        print(f"[ERROR] Failed to go back to stoplist: {e}")

@news_router.callback_query(F.data == "close_stoplist")
async def close_stoplist(callback: CallbackQuery):
    """Закрывает стоп-лист"""
    await callback.answer("Закрыто")
    try:
        await callback.message.delete()
    except:
        pass
