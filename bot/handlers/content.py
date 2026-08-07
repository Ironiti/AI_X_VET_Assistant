from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import html

from src.database.db_init import db
from bot.keyboards import (
    DOWNLOAD_FORMS_BUTTON_ALIASES,
    TUBE_GALLERY_BUTTON_ALIASES,
    get_main_menu_kb,
    get_menu_by_role,
)

content_router = Router()

# ============================================================
# ГАЛЕРЕЯ ПРОБИРОК - ПОКАЗ ПОЛЬЗОВАТЕЛЯМ
# ============================================================

@content_router.message(F.text.in_(TUBE_GALLERY_BUTTON_ALIASES))
async def show_gallery(message: Message):
    """Показ галереи пользователю"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return
    
    items = await db.get_all_gallery_items()
    
    if not items:
        await message.answer(
            "🖼️ Галерея пока пуста.\n"
            "Администратор еще не добавил фотографии.",
            reply_markup=get_menu_by_role(user.get('role', 'user'))
        )
        return
    
    await message.answer(
        "🖼️ <b>Галерея пробирок и контейнеров</b>\n\n"
        "Выберите интересующий вас элемент:",
        parse_mode="HTML",
        reply_markup=create_gallery_keyboard(items)
    )

def create_gallery_keyboard(items):
    """Создает inline клавиатуру для галереи"""
    keyboard = []
    
    for item in items:
        keyboard.append([
            InlineKeyboardButton(
                text=item['title'],
                callback_data=f"gallery_item_{item['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_gallery")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@content_router.callback_query(F.data.startswith("gallery_item_"))
async def show_gallery_item(callback: CallbackQuery):
    """Показывает конкретный элемент галереи"""
    await callback.answer()
    
    try:
        item_id = int(callback.data.split("_")[-1])
        item = await db.get_gallery_item(item_id)
        
        if not item:
            await callback.answer("Элемент не найден", show_alert=True)
            return
        
        caption = f"📌 <b>{html.escape(item['title'])}</b>"
        if item.get('description'):
            caption += f"\n\n📝 {html.escape(item['description'])}"
        
        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к галерее", callback_data="back_to_gallery")],
                [InlineKeyboardButton(text="🔙 Закрыть всё", callback_data="close_gallery_and_photo")]
            ]
        )
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer_photo(
            photo=item['file_id'],
            caption=caption,
            parse_mode="HTML",
            reply_markup=back_keyboard
        )
        
    except Exception as e:
        print(f"[ERROR] Failed to show gallery item: {e}")
        await callback.answer("Ошибка при загрузке элемента", show_alert=True)

@content_router.callback_query(F.data == "back_to_gallery")
async def back_to_gallery(callback: CallbackQuery):
    """Возврат к списку галереи"""
    await callback.answer()
    
    items = await db.get_all_gallery_items()
    
    if items:
        try:
            await callback.message.delete()
            
            await callback.message.answer(
                "🖼️ <b>Галерея пробирок и контейнеров</b>\n\n"
                "Выберите интересующий вас элемент:",
                parse_mode="HTML",
                reply_markup=create_gallery_keyboard(items)
            )
        except Exception as e:
            print(f"[ERROR] Failed to go back to gallery: {e}")

@content_router.callback_query(F.data == "close_gallery")
async def close_gallery(callback: CallbackQuery):
    """Закрывает галерею"""
    await callback.answer("Галерея закрыта")
    try:
        await callback.message.delete()
    except:
        pass

@content_router.callback_query(F.data == "close_gallery_and_photo")
async def close_gallery_and_photo(callback: CallbackQuery):
    """Закрывает фото из галереи полностью"""
    await callback.answer("Закрыто")
    try:
        await callback.message.delete()
    except:
        pass

# ============================================================
# ССЫЛКИ НА БЛАНКИ - ПОКАЗ ПОЛЬЗОВАТЕЛЯМ
# ============================================================

@content_router.message(F.text.in_(DOWNLOAD_FORMS_BUTTON_ALIASES))
async def show_blanks(message: Message):
    """Показ бланков пользователю"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return
    
    items = await db.get_all_blank_documents()
    
    if not items:
        await message.answer(
            "📄 Список бланков пока пуст.\n"
            "Администратор еще не добавил документы бланков.",
            reply_markup=get_menu_by_role(user.get('role', 'user'))
        )
        return
    
    await message.answer(
        "📄 <b>Бланки и документы</b>\n\n"
        "Выберите нужный бланк для получения:",
        parse_mode="HTML",
        reply_markup=create_blanks_keyboard(items)
    )

def create_blanks_keyboard(items):
    """Создает inline клавиатуру для бланков"""
    keyboard = []
    
    for item in items:
        keyboard.append([
            InlineKeyboardButton(
                text=item['title'],
                callback_data=f"blank_doc_{item['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_blanks")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@content_router.callback_query(F.data.startswith("blank_doc_"))
async def send_blank_document(callback: CallbackQuery):
    """Отправляет документ бланка пользователю"""
    await callback.answer()
    
    try:
        blank_id = int(callback.data.split("_")[-1])
        blank = await db.get_blank_document(blank_id)
        
        if not blank:
            await callback.answer("Документ не найден", show_alert=True)
            return
        
        # Удаляем список бланков
        try:
            await callback.message.delete()
        except:
            pass
        
        # Формируем caption
        caption = f"📄 <b>{html.escape(blank['title'])}</b>"
        if blank.get('description'):
            caption += f"\n\n📝 {html.escape(blank['description'])}"
        
        # Кнопки навигации
        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="back_to_blanks")],
                [InlineKeyboardButton(text="🔙 Закрыть всё", callback_data="close_blanks_and_doc")]
            ]
        )
        
        # Отправляем документ с навигацией
        await callback.message.answer_document(
            document=blank['file_id'],
            caption=caption,
            parse_mode="HTML",
            reply_markup=back_keyboard
        )
        
    except Exception as e:
        print(f"[ERROR] Failed to send blank document: {e}")
        await callback.answer("Ошибка при отправке документа", show_alert=True)

@content_router.callback_query(F.data == "back_to_blanks")
async def back_to_blanks(callback: CallbackQuery):
    """Возврат к списку бланков"""
    await callback.answer()
    
    items = await db.get_all_blank_documents()
    
    if items:
        try:
            # Удаляем документ
            await callback.message.delete()
            
            # Показываем список снова
            await callback.message.answer(
                "📄 <b>Бланки и документы</b>\n\n"
                "Выберите нужный бланк для получения:",
                parse_mode="HTML",
                reply_markup=create_blanks_keyboard(items)
            )
        except Exception as e:
            print(f"[ERROR] Failed to go back to blanks: {e}")

@content_router.callback_query(F.data == "close_blanks")
async def close_blanks(callback: CallbackQuery):
    """Закрывает список бланков"""
    await callback.answer("Список закрыт")
    try:
        await callback.message.delete()
    except:
        pass

@content_router.callback_query(F.data == "close_blanks_and_doc")
async def close_blanks_and_doc(callback: CallbackQuery):
    """Закрывает документ бланка полностью"""
    await callback.answer("Закрыто")
    try:
        await callback.message.delete()
    except:
        pass
