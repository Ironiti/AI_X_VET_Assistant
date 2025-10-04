import re
import asyncio
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_kb, get_menu_by_role, get_phone_kb, get_feedback_type_kb, get_back_to_menu_kb
from utils.email_sender import send_callback_email, send_feedback_email

from src.database.db_init import db

feedback_router = Router()

class CallbackStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_message = State()

class FeedbackStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_message = State()

def format_phone_number(phone: str, country: str = 'BY'):
    """Форматирование телефонного номера с учетом страны"""
    digits = re.sub(r'\D', '', phone)
    
    if country == 'BY':
        # Добавляем код страны если его нет
        if len(digits) == 9:
            digits = '375' + digits
        if len(digits) == 12 and digits.startswith('375'):
            return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:10]}-{digits[10:12]}"
    
    elif country == 'RU':
        # Для России
        if len(digits) == 10:
            digits = '7' + digits
        elif len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        if len(digits) == 11 and digits.startswith('7'):
            return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    
    elif country == 'KZ':
        # Для Казахстана
        if len(digits) == 10 and digits.startswith('7'):
            digits = '7' + digits
        elif len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        if len(digits) == 11 and digits.startswith('77'):
            return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    elif country == 'AM':
        # Для Армении
        if len(digits) == 8:
            digits = '374' + digits
        if len(digits) == 11 and digits.startswith('374'):
            return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:11]}" 
    return phone  

def validate_phone_number(phone: str, country: str = 'BY'):
    """Валидация телефонного номера с учетом страны"""
    digits = re.sub(r'\D', '', phone)
    
    if country == 'BY':
        # Беларусь: +375 XX XXX-XX-XX
        return bool(re.match(r'^(375)?[0-9]{9}$', digits))
    elif country == 'RU':
        # Россия: +7 XXX XXX-XX-XX
        return bool(re.match(r'^[78]?[0-9]{10}$', digits))
    elif country == 'KZ':
        # Казахстан: +7 7XX XXX-XX-XX
        return bool(re.match(r'^[78]?7[0-9]{9}$', digits))
    elif country == 'AM':
        # Армения: +374 XX XXX-XXX
        return bool(re.match(r'^(374)?[0-9]{8}$', digits))
    return False

@feedback_router.message(F.text == "📞 Заказать звонок")
async def request_callback(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return

    # Получаем страну пользователя
    country = user['country'] if 'country' in user.keys() else 'BY'
    await state.update_data(user_country=country)
    
    # Формируем подсказку по формату
    phone_formats = {
        'BY': "+375 (XX) XXX-XX-XX",
        'RU': "+7 (XXX) XXX-XX-XX",
        'KZ': "+7 (7XX) XXX-XX-XX",
        'AM': "+374 (XX) XXX-XXX"
    }
    
    format_hint = phone_formats.get(country, phone_formats['BY'])
    
    await message.answer(
        f"📞 Заказ обратного звонка\n\n"
        f"Пожалуйста, отправьте ваш номер телефона или введите вручную.\n"
        f"Формат для вашей страны: {format_hint}",
        reply_markup=get_phone_kb()
    )
    await state.set_state(CallbackStates.waiting_for_phone)

@feedback_router.message(CallbackStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        return

    data = await state.get_data()
    country = data.get('user_country', 'BY')
    phone = ""

    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
    else:
        phone = message.text
        if not validate_phone_number(phone, country):
            phone_examples = {
                'BY': "375291234567 или +375 29 123-45-67",
                'RU': "79123456789 или +7 912 345-67-89",
                'KZ': "77012345678 или +7 701 234-56-78",
                'AM': "37477123456 или +374 77 123-456"
            }
            example = phone_examples.get(country, phone_examples['BY'])
            
            await message.answer(
                f"❌ Неверный формат номера телефона.\n"
                f"Пожалуйста, введите номер в формате:\n"
                f"{example}",
                reply_markup=get_phone_kb()
            )
            return
        
        phone = format_phone_number(phone, country)

    await state.update_data(phone=phone)
    await message.answer(
        "Отлично! Теперь напишите ваше сообщение.\n"
        "Опишите причину обращения, удобное время для звонка и любую другую важную информацию:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(CallbackStates.waiting_for_message)

@feedback_router.message(CallbackStates.waiting_for_message)
async def process_callback_message(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        print(f"[INFO] User {user_id} cancelled callback message")
        return

    data = await state.get_data()
    phone = data.get('phone')
    user = await db.get_user(user_id)
    
    # Преобразуем Row в словарь
    user_dict = dict(user) if user else {}

    print(f"[INFO] Sending callback email for user {user_id}")
    email_sent = await send_callback_email(user_dict, phone, message.text)

    if email_sent:
        print(f"[INFO] Callback email sent for user {user_id}")
    else:
        print(f"[WARN] Callback email failed for user {user_id}, fallback to acceptance message")

    await db.add_request_stat(user_id, "callback_request", f"Телефон: {phone}, Сообщение: {message.text[:100]}...")
    print(f"[INFO] Callback stat saved for user {user_id}")

    # Обычный flow - если не нужно возвращаться в диалог
    user_role = user['role'] if user else 'user'
    await message.answer(
        "✅ Ваша заявка на обратный звонок успешно отправлена!\n\n"
        f"📞 Телефон: {phone}\n💬 Сообщение: {message.text}\n\n"
        "Наш специалист свяжется с вами в ближайшее время.",
        reply_markup=get_menu_by_role(user_role)
    )
    await state.clear()
    print(f"[INFO] State cleared for user {user_id}")

@feedback_router.message(F.text == "💡 Предложения и пожелания")
async def start_feedback(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} requested feedback submission")

    user = await db.get_user(user_id)
    if not user:
        print(f"[WARN] User {user_id} not registered, prompting /start")
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return

    await message.answer("Выберите тип обращения:", reply_markup=get_feedback_type_kb())
    await state.set_state(FeedbackStates.waiting_for_type)
    print(f"[INFO] State set to waiting_for_type for user {user_id}")

@feedback_router.message(FeedbackStates.waiting_for_type)
async def process_feedback_type(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        print(f"[INFO] User {user_id} cancelled feedback type selection")
        return

    if message.text not in ["💡 Предложение", "⚠️ Жалоба"]:
        print(f"[WARN] User {user_id} entered invalid feedback type: {message.text}")
        await message.answer("Пожалуйста, выберите тип обращения из предложенных вариантов.", reply_markup=get_feedback_type_kb())
        return

    feedback_type = "suggestion" if message.text == "💡 Предложение" else "complaint"
    await state.update_data(feedback_type=feedback_type)
    print(f"[INFO] User {user_id} selected feedback type: {feedback_type}")

    await message.answer(
        f"Вы выбрали: {message.text}\n\n"
        "Пожалуйста, опишите ваше обращение подробно:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(FeedbackStates.waiting_for_message)
    print(f"[INFO] State set to waiting_for_message for user {user_id}")

@feedback_router.message(FeedbackStates.waiting_for_message)
async def process_feedback_message(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        print(f"[INFO] User {user_id} cancelled feedback message")
        return

    data = await state.get_data()
    feedback_type = data.get('feedback_type')
    user = await db.get_user(user_id)
    
    # Преобразуем Row в словарь
    user_dict = dict(user) if user else {}

    await db.add_feedback(user_id=user_id, feedback_type=feedback_type, message=message.text)
    print(f"[INFO] Feedback saved to DB for user {user_id}")

    await send_feedback_email(user_dict, feedback_type, message.text)
    print(f"[INFO] Feedback email sent for user {user_id}")

    type_text = "предложение" if feedback_type == "suggestion" else "жалоба"
    user_role = user['role'] if user else 'user'
    await message.answer(
        f"✅ Ваше {type_text} успешно отправлено!\n\n"
        "Мы обязательно рассмотрим ваше обращение и примем необходимые меры.\nСпасибо за обратную связь!",
        reply_markup=get_menu_by_role(user_role)
    )
    await state.clear()
    print(f"[INFO] State cleared for user {user_id}")
