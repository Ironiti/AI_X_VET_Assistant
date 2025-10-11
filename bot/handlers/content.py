from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import html

from src.database.db_init import db
from bot.keyboards import get_dialog_kb

content_router = Router()

# ============================================================
# ГАЛЕРЕЯ ПРОБИРОК
# ============================================================

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
    """Возврат к списку галереи - редактируем сообщение вместо создания нового"""
    await callback.answer()
    
    items = await db.get_all_gallery_items()
    
    if items:
        try:
            # Пытаемся отредактировать текущее сообщение с фото
            # Telegram не позволяет редактировать фото в текст, поэтому удаляем и создаем новое
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
# АЛЬТЕРНАТИВНОЕ РЕШЕНИЕ - Используем медиа группы
# ============================================================

async def show_gallery_with_preview(message: Message, items: list):
    """Показывает галерею с превью изображений"""
    if not items:
        return
    
    # Создаем текст с нумерованным списком
    text = "🖼️ <b>Галерея пробирок и контейнеров</b>\n\n"
    
    keyboard = []
    for i, item in enumerate(items, 1):
        text += f"{i}. {html.escape(item['title'])}\n"
        if item.get('description'):
            text += f"   <i>{html.escape(item['description'][:50])}...</i>\n"
        text += "\n"
        
        # Кнопка для просмотра
        keyboard.append([
            InlineKeyboardButton(
                text=f"👁 Посмотреть: {item['title'][:30]}...",
                callback_data=f"view_gallery_{item['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_gallery")
    ])
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@content_router.callback_query(F.data.startswith("view_gallery_"))
async def view_gallery_item_inline(callback: CallbackQuery):
    """Показывает элемент галереи через редактирование сообщения"""
    await callback.answer()
    
    try:
        item_id = int(callback.data.split("_")[-1])
        item = await db.get_gallery_item(item_id)
        
        if not item:
            await callback.answer("Элемент не найден", show_alert=True)
            return
        
        # Отправляем фото отдельным сообщением с кнопкой удаления
        close_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="❌ Закрыть фото", callback_data=f"close_photo_{item_id}")
            ]]
        )
        
        caption = f"📌 <b>{html.escape(item['title'])}</b>"
        if item.get('description'):
            caption += f"\n\n📝 {html.escape(item['description'])}"
        
        # Отправляем фото
        await callback.message.answer_photo(
            photo=item['file_id'],
            caption=caption,
            parse_mode="HTML",
            reply_markup=close_keyboard
        )
        
    except Exception as e:
        print(f"[ERROR] Failed to view gallery item: {e}")
        await callback.answer("Ошибка при загрузке", show_alert=True)

@content_router.callback_query(F.data.startswith("close_photo_"))
async def close_photo_only(callback: CallbackQuery):
    """Закрывает только фото, оставляя список галереи"""
    await callback.answer("Фото закрыто")
    try:
        await callback.message.delete()
    except:
        pass

# ============================================================
# ССЫЛКИ НА БЛАНКИ
# ============================================================

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
