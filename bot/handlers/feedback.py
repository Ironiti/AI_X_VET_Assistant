import re
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_kb, get_menu_by_role, get_phone_kb, get_feedback_type_kb
from utils.email_sender import send_callback_email, send_feedback_email

from src.database.db_init import db

feedback_router = Router()

class CallbackStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_message = State()

class FeedbackStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_message = State()

def format_phone_number(phone: str, country: str = 'RU'):
    digits = re.sub(r'\\D', '', phone)
    if country == 'BY':
        if len(digits) == 9:
            digits = '375' + digits
        elif len(digits) == 11 and digits.startswith('80'):
            digits = '375' + digits[2:]
        if digits.startswith('375'):
            return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:10]}-{digits[10:12]}"
    else:
        if len(digits) == 10:
            digits = '7' + digits
        elif len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        if digits.startswith('7'):
            return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return '+' + digits

def validate_phone_number(phone: str, country: str = 'RU'):
    digits = re.sub(r'\\D', '', phone)
    if country == 'BY':
        return bool(re.match(r'^(375|80)?\\d{9}$', digits))
    else:
        return bool(re.match(r'^[78]?\\d{10}$', digits))

@feedback_router.message(F.text == "📞 Обратная связь")
async def request_callback(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} requested callback")

    user = await db.get_user(user_id)
    if not user:
        print(f"[WARN] User {user_id} not registered, prompting /start")
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return

    if user['role'] == 'staff':
        print(f"[WARN] User {user_id} is staff, callback denied")
        await message.answer("Эта функция недоступна для сотрудников.", reply_markup=get_menu_by_role(user['role']))
        return

    country = user['country'] or 'RU'
    print(f"[INFO] User {user_id} country detected as {country}")

    country_name = {'RU': 'Россия', 'BY': 'Беларусь', 'KZ': 'Казахстан'}.get(country, 'Россия')
    phone_format = {'RU': '+7 (XXX) XXX-XX-XX', 'BY': '+375 (XX) XXX-XX-XX', 'KZ': '+7 (XXX) XXX-XX-XX'}.get(country, '+7 (XXX) XXX-XX-XX')

    await message.answer(
        f"📞 Заказ обратного звонка\n🌍 Ваша страна: {country_name}\n\n"
        f"Пожалуйста, отправьте ваш номер телефона или введите вручную.\nФормат: {phone_format}",
        reply_markup=get_phone_kb()
    )
    await state.set_state(CallbackStates.waiting_for_phone)
    await state.update_data(user_country=country)
    print(f"[INFO] State set to waiting_for_phone for user {user_id}")

@feedback_router.message(CallbackStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "❌ Отмена":
        await state.clear()
        user = await db.get_user(user_id)
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user['role']))
        print(f"[INFO] User {user_id} cancelled phone input")
        return

    data = await state.get_data()
    country = data.get('user_country', 'RU')
    phone = ""

    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
    else:
        phone = message.text
        if not validate_phone_number(phone, country):
            print(f"[WARN] User {user_id} entered invalid phone: {phone}")
            phone_example = {
                'RU': '+7 (912) 345-67-89 или 89123456789',
                'BY': '+375 (29) 123-45-67 или 80291234567',
                'KZ': '+7 (701) 234-56-78 или 87012345678'
            }.get(country, '+7 (XXX) XXX-XX-XX')
            await message.answer(f"❌ Неверный формат номера телефона.\nПожалуйста, введите номер в формате:\n{phone_example}", reply_markup=get_phone_kb())
            return
        phone = format_phone_number(phone, country)

    await state.update_data(phone=phone)
    print(f"[INFO] User {user_id} phone saved: {phone}")

    await message.answer(
        "Отлично! Теперь напишите ваше сообщение.\nОпишите причину обращения, удобное время для звонка и любую другую важную информацию:",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(CallbackStates.waiting_for_message)
    print(f"[INFO] State set to waiting_for_message for user {user_id}")

@feedback_router.message(CallbackStates.waiting_for_message)
async def process_callback_message(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "❌ Отмена":
        await state.clear()
        user = await db.get_user(user_id)
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user['role']))
        print(f"[INFO] User {user_id} cancelled callback message")
        return

    data = await state.get_data()
    phone = data.get('phone')
    user = await db.get_user(user_id)

    print(f"[INFO] Sending callback email for user {user_id}")
    email_sent = await send_callback_email(user, phone, message.text)

    if email_sent:
        print(f"[INFO] Callback email sent for user {user_id}")
    else:
        print(f"[WARN] Callback email failed for user {user_id}, fallback to acceptance message")

    await db.add_request_stat(user_id, "callback_request", f"Телефон: {phone}, Сообщение: {message.text[:100]}...")
    print(f"[INFO] Callback stat saved for user {user_id}")

    await message.answer(
        "✅ Ваша заявка на обратный звонок успешно отправлена!\n\n"
        f"📞 Телефон: {phone}\n💬 Сообщение: {message.text}\n\n"
        "Наш администратор свяжется с вами в ближайшее время.",
        reply_markup=get_menu_by_role(user['role'])
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

    if user['role'] == 'staff':
        print(f"[WARN] User {user_id} is staff, feedback denied")
        await message.answer("Эта функция недоступна для сотрудников.", reply_markup=get_menu_by_role(user['role']))
        return

    await message.answer("Выберите тип обращения:", reply_markup=get_feedback_type_kb())
    await state.set_state(FeedbackStates.waiting_for_type)
    print(f"[INFO] State set to waiting_for_type for user {user_id}")

@feedback_router.message(FeedbackStates.waiting_for_type)
async def process_feedback_type(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "❌ Отмена":
        await state.clear()
        user = await db.get_user(user_id)
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user['role']))
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
        reply_markup=get_cancel_kb()
    )
    await state.set_state(FeedbackStates.waiting_for_message)
    print(f"[INFO] State set to waiting_for_message for user {user_id}")

@feedback_router.message(FeedbackStates.waiting_for_message)
async def process_feedback_message(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "❌ Отмена":
        await state.clear()
        user = await db.get_user(user_id)
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user['role']))
        print(f"[INFO] User {user_id} cancelled feedback message")
        return

    data = await state.get_data()
    feedback_type = data.get('feedback_type')
    user = await db.get_user(user_id)

    await db.add_feedback(user_id=user_id, feedback_type=feedback_type, message=message.text)
    print(f"[INFO] Feedback saved to DB for user {user_id}")

    await send_feedback_email(user, feedback_type, message.text)
    print(f"[INFO] Feedback email sent for user {user_id}")

    type_text = "предложение" if feedback_type == "suggestion" else "жалоба"
    await message.answer(
        f"✅ Ваше {type_text} успешно отправлено!\n\n"
        "Мы обязательно рассмотрим ваше обращение и примем необходимые меры.\nСпасибо за обратную связь!",
        reply_markup=get_menu_by_role(user['role'])
    )
    await state.clear()
    print(f"[INFO] State cleared for user {user_id}")
