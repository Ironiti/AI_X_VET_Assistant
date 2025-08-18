import random
import string
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
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
