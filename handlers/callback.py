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

router = Router()
db = Database(DATABASE_PATH)

class CallbackStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_message = State()

def format_phone_number(phone: str, country: str = 'RU'):
    """Форматирование номера телефона в зависимости от страны"""
    # Убираем все символы кроме цифр
    digits = re.sub(r'\D', '', phone)
    
    if country == 'BY':  # Беларусь
        if len(digits) == 9:
            digits = '375' + digits
        elif len(digits) == 11 and digits.startswith('80'):
            digits = '375' + digits[2:]
        
        if digits.startswith('375'):
            return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:10]}-{digits[10:12]}"
    
    else:  # Россия и Казахстан
        if len(digits) == 10:
            digits = '7' + digits
        elif len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        
        if digits.startswith('7'):
            return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    
    return '+' + digits

def validate_phone_number(phone: str, country: str = 'RU'):
    """Валидация номера телефона в зависимости от страны"""
    # Убираем все символы кроме цифр
    digits = re.sub(r'\D', '', phone)
    
    if country == 'BY':  # Беларусь
        # Принимаем форматы: 375XXXXXXXXX, 80XXXXXXXXX, XXXXXXXXX
        if re.match(r'^(375|80)?\d{9}$', digits):
            return True
    else:  # Россия и Казахстан
        # Принимаем форматы: 7XXXXXXXXXX, 8XXXXXXXXXX, XXXXXXXXXX
        if re.match(r'^[78]?\d{10}$', digits):
            return True
    
    return False

@router.message(F.text == "📞 Заказать звонок")
async def request_callback(message: Message, state: FSMContext):
    # Проверяем, зарегистрирован ли пользователь
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer(
            "Для заказа звонка необходимо пройти регистрацию.\n"
            "Используйте команду /start",
            reply_markup=get_main_menu_kb()
        )
        return
    
    # Обращаемся к полям Row объекта через квадратные скобки
    country = user['country'] if user['country'] else 'RU'
    country_name = {
        'RU': 'Россия',
        'BY': 'Беларусь', 
        'KZ': 'Казахстан'
    }.get(country, 'Россия')
    
    phone_format = {
        'RU': '+7 (XXX) XXX-XX-XX',
        'BY': '+375 (XX) XXX-XX-XX',
        'KZ': '+7 (XXX) XXX-XX-XX'
    }.get(country, '+7 (XXX) XXX-XX-XX')
    
    await message.answer(
        f"📞 Заказ обратного звонка\n"
        f"🌍 Ваша страна: {country_name}\n\n"
        f"Пожалуйста, отправьте ваш номер телефона или введите вручную.\n"
        f"Формат: {phone_format}",
        reply_markup=get_phone_kb()
    )
    await state.set_state(CallbackStates.waiting_for_phone)
    await state.update_data(user_country=country)

@router.message(CallbackStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_main_menu_kb())
        return
        
    data = await state.get_data()
    country = data.get('user_country', 'RU')
    phone = ""
    
    # Если пользователь поделился контактом
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
    else:
        # Если ввел вручную
        phone = message.text
        
        # Валидация номера
        if not validate_phone_number(phone, country):
            phone_example = {
                'RU': '+7 (912) 345-67-89 или 89123456789',
                'BY': '+375 (29) 123-45-67 или 80291234567',
                'KZ': '+7 (701) 234-56-78 или 87012345678'
            }.get(country, '+7 (XXX) XXX-XX-XX')
            
            await message.answer(
                f"❌ Неверный формат номера телефона.\n"
                f"Пожалуйста, введите номер в формате:\n"
                f"{phone_example}",
                reply_markup=get_phone_kb()
            )
            return
        
        # Форматируем номер
        phone = format_phone_number(phone, country)
    
    await state.update_data(phone=phone)
    await message.answer(
        "Отлично! Теперь напишите ваше сообщение.\n"
        "Опишите причину обращения, удобное время для звонка и любую другую важную информацию:",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(CallbackStates.waiting_for_message)

@router.message(CallbackStates.waiting_for_message)
async def process_message(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Операция отменена.", reply_markup=get_main_menu_kb())
        return
        
    data = await state.get_data()
    phone = data.get('phone')
    
    # Получаем данные пользователя из БД
    user = await db.get_user(message.from_user.id)
    
    # Преобразуем Row в словарь для email_sender
    user_data = {
        'telegram_id': user['telegram_id'],
        'username': user['username'],
        'client_code': user['client_code'],
        'pet_name': user['pet_name'],
        'pet_type': user['pet_type'],
        'country': user['country'] if user['country'] else 'RU'
    }
    
    # Отправляем email
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
    
    # Сохраняем в статистику
    await db.add_request_stat(
        message.from_user.id,
        "callback_request",
        f"Телефон: {phone}, Сообщение: {message.text[:100]}..."
    )
    
    await message.answer(response, reply_markup=get_main_menu_kb())
    await state.clear()