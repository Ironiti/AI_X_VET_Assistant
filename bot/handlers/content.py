from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import html

from src.database.db_init import db
from bot.keyboards import get_main_menu_kb, get_menu_by_role

content_router = Router()

# ============================================================
# ГАЛЕРЕЯ ПРОБИРОК - ПОКАЗ ПОЛЬЗОВАТЕЛЯМ
# ============================================================

@content_router.message(F.text == "🖼️ Галерея пробирок и контейнеров")
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
        
        # Клавиатура для возврата к списку
        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к галерее", callback_data="back_to_gallery")],
                [InlineKeyboardButton(text="🔙 Закрыть всё", callback_data="close_gallery_and_photo")]
            ]
        )
        
        # ВАЖНО: Удаляем старое сообщение со списком галереи
        try:
            await callback.message.delete()
        except:
            pass
        
        # Отправляем фото как новое сообщение
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
            # Удаляем фото и показываем список
            await callback.message.delete()
            
            # Отправляем список галереи
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

@content_router.message(F.text == "📄 Ссылки на бланки")
async def show_blanks(message: Message):
    """Показ бланков пользователю"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return
    
    items = await db.get_all_blank_links()
    
    if not items:
        await message.answer(
            "📄 Список бланков пока пуст.\n"
            "Администратор еще не добавил ссылки на бланки.",
            reply_markup=get_menu_by_role(user.get('role', 'user'))
        )
        return
    
    await message.answer(
        "📄 <b>Ссылки на бланки</b>\n\n"
        "Выберите нужный бланк для открытия:",
        parse_mode="HTML",
        reply_markup=create_blanks_keyboard(items)
    )

def create_blanks_keyboard(items):
    """Создает inline клавиатуру для бланков"""
    keyboard = []
    
    for item in items:
        # Кнопки с URL открывают ссылку напрямую
        keyboard.append([
            InlineKeyboardButton(
                text=item['title'],
                url=item['url']
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_blanks")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@content_router.callback_query(F.data == "close_blanks")
async def close_blanks(callback: CallbackQuery):
    """Закрывает список бланков"""
    await callback.answer("Список закрыт")
    try:
        await callback.message.delete()
    except:
        pass
