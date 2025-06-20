from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Database
from keyboards.reply import get_cancel_kb, get_main_menu_kb, get_phone_kb
from utils.email_sender import send_callback_email
from config import DATABASE_PATH
import re

get_phone_router = Router()
db = Database(DATABASE_PATH)

class CallbackStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_message = State()

@get_phone_router.message(F.text == "📞 Заказать звонок")
async def request_callback(message: Message, state: FSMContext):
    user_exists = await db.user_exists(message.from_user.id)
    
    if not user_exists:
        await message.answer(
            "Для заказа звонка необходимо пройти регистрацию.\n"
            "Используйте команду /start",
            reply_markup=get_main_menu_kb()
        )
        return
    
    await message.answer(
        "📞 Заказ обратного звонка\n\n"
        "Пожалуйста, отправьте ваш номер телефона или введите вручную.\n"
        "Формат: +7 (XXX) XXX-XX-XX",
        reply_markup=get_phone_kb()
    )
    await state.set_state(CallbackStates.waiting_for_phone)

@get_phone_router.message(CallbackStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    phone = ""
    
    # if shared contact
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
    # if message
    else:
        phone = message.text
        phone_digits = re.sub(r'[^\d+]', '', phone)
        
        if not re.match(r'^\+?[78]?\d{10}$', phone_digits):
            await message.answer(
                "❌ Неверный формат номера телефона.\n"
                "Пожалуйста, введите номер в формате:\n"
                "+7 (XXX) XXX-XX-XX или 8XXXXXXXXXX",
                reply_markup=get_phone_kb()
            )
            return
        
        if phone_digits.startswith('8'):
            phone_digits = '+7' + phone_digits[1:]
        elif phone_digits.startswith('7'):
            phone_digits = '+' + phone_digits
        elif not phone_digits.startswith('+'):
            phone_digits = '+7' + phone_digits
            
        phone = phone_digits
    
    await state.update_data(phone=phone)
    await message.answer(
        "Отлично! Теперь напишите ваше сообщение.\n"
        "Опишите причину обращения, удобное время для звонка и любую другую важную информацию:",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(CallbackStates.waiting_for_message)

@get_phone_router.message(CallbackStates.waiting_for_message)
async def process_message(message: Message, state: FSMContext):
    data = await state.get_data()
    phone = data.get('phone')
    
    user = await db.get_user(message.from_user.id)
    user_data = {
        'telegram_id': user['telegram_id'],
        'username': user['username'],
        'client_code': user['client_code'],
        'pet_name': user['pet_name'],
        'pet_type': user['pet_type']
    }
    
    email_sent = await send_callback_email(user_data, phone, message.text)
    
    if email_sent:
        response = (
            "✅ Ваша заявка на обратный звонок успешно отправлена!\n\n"
            f"📞 Телефон: {phone}\n"
            f"💬 Сообщение: {message.text}\n\n"
            "Наш администратор свяжется с вами в ближайшее время."
        )
    else:
        response = (
            "✅ Ваша заявка на обратный звонок принята!\n\n"
            f"📞 Телефон: {phone}\n"
            f"💬 Сообщение: {message.text}\n\n"
            "Наш администратор свяжется с вами в ближайшее время.\n\n"
            "⚠️ Примечание: возникла проблема с отправкой уведомления, "
            "но ваша заявка сохранена."
        )
    
    await db.add_request_stat(
        message.from_user.id,
        "callback_request",
        f"Телефон: {phone}, Сообщение: {message.text[:100]}..."
    )
    
    await message.answer(response, reply_markup=get_main_menu_kb())
    await state.clear()
