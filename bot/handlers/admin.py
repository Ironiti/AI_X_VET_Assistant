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
    waiting_for_message = State()

class SystemStates(StatesGroup):
    in_system_menu = State()

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
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        if message.text == "📊 Полная выгрузка":
            excel_data = await exporter.export_all_data()
            filename = f"full_{filename}"
            caption = "📊 Полная выгрузка данных системы"
        
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
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при создании выгрузки: {str(e)}",
            reply_markup=get_admin_menu_kb()
        )
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
        "📝 Введите текст сообщения для рассылки:\n\n"
        "Поддерживается HTML-форматирование:\n"
        "• <b>жирный</b>\n"
        "• <i>курсив</i>\n"
        "• <code>код</code>",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(BroadcastStates.waiting_for_message)

@admin_router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_admin_menu_kb())
        return
    
    data = await state.get_data()
    broadcast_type = data['broadcast_type']
    
    recipients = await db.get_broadcast_recipients(broadcast_type)
    
    if not recipients:
        await message.answer(
            "❌ Не найдено получателей для рассылки.",
            reply_markup=get_admin_menu_kb()
        )
        await state.clear()
        return
    
    await message.answer(
        f"📢 Рассылка будет отправлена {len(recipients)} получателям.\n\n"
        f"Текст сообщения:\n{message.text}\n\n"
        "Начинаю рассылку..."
    )
    
    from bot.handlers import bot
    success_count = 0
    failed_count = 0
    
    for recipient_id in recipients:
        try:
            await bot.send_message(
                recipient_id,
                f"📢 <b>Сообщение от администрации VET UNION</b>\n\n{message.text}",
                parse_mode="HTML"
            )
            success_count += 1
            await asyncio.sleep(0.1)
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
async def show_all_requests(message: Message):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    recent_feedback = await db.get_recent_feedback(limit=5)
    
    if not recent_feedback:
        await message.answer(
            "Обращений пока нет.",
            reply_markup=get_admin_menu_kb()
        )
        return
    
    text = "📋 Последние 5 обращений:\n\n"
    
    for feedback in recent_feedback:
        feedback_type = "💡 Предложение" if feedback['feedback_type'] == 'suggestion' else "⚠️ Жалоба"
        status = {
            'new': '🆕 Новое',
            'in_progress': '⏳ В работе',
            'resolved': '✅ Решено'
        }.get(feedback['status'], feedback['status'])
        
        text += f"{feedback_type} | {status}\n"
        text += f"👤 {feedback.get('user_name', 'Неизвестный')}\n"
        text += f"📝 {feedback['message'][:100]}{'...' if len(feedback['message']) > 100 else ''}\n"
        text += f"📅 {feedback['timestamp']}\n"
        text += "─" * 30 + "\n"
    
    await message.answer(text, reply_markup=get_admin_menu_kb())

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