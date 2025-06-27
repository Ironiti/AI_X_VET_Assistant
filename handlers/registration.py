from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Database
from keyboards.reply import get_cancel_kb, get_country_kb, get_pet_type_kb, get_main_menu_kb
from config import DATABASE_PATH
import re
import logging

router = Router()
db = Database(DATABASE_PATH)
logger = logging.getLogger(__name__)

class RegistrationStates(StatesGroup):
    waiting_for_country = State()
    waiting_for_name = State()
    waiting_for_client_code = State()
    waiting_for_pet_name = State()
    waiting_for_pet_type = State()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    user_exists = await db.user_exists(message.from_user.id)
    
    if user_exists:
        await message.answer(
            "Вы уже зарегистрированы! 🎉\n"
            "Используйте меню для дальнейшей работы.",
            reply_markup=get_main_menu_kb()
        )
    else:
        await message.answer(
            "Добро пожаловать в бот ветеринарной клиники! 🏥\n"
            "Давайте пройдем регистрацию.\n\n"
            "Выберите вашу страну:",
            reply_markup=get_country_kb()
        )
        await state.set_state(RegistrationStates.waiting_for_country)

@router.message(StateFilter(RegistrationStates), F.text == "❌ Отмена")
async def cancel_registration(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Регистрация отменена. Для начала регистрации используйте /start",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(RegistrationStates.waiting_for_country)
async def process_country(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        return
    
    country_map = {
        "🇷🇺 Россия": "RU",
        "🇧🇾 Беларусь": "BY", 
        "🇰🇿 Казахстан": "KZ"
    }
    
    if message.text not in country_map:
        await message.answer(
            "❌ Пожалуйста, выберите страну из предложенных вариантов",
            reply_markup=get_country_kb()
        )
        return
    
    await state.update_data(country=country_map[message.text], country_name=message.text)
    await message.answer(
        "Введите ваше имя:\n"
        "⚠️ Используйте только буквы и пробелы (2-50 символов)",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_name)

@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        return
        
    name = message.text.strip()
    
    if len(name) < 2:
        await message.answer(
            "❌ Имя слишком короткое. Минимум 2 символа.\n"
            "Попробуйте еще раз:"
        )
        return
    
    if len(name) > 50:
        await message.answer(
            "❌ Имя слишком длинное. Максимум 50 символов.\n"
            "Попробуйте еще раз:"
        )
        return
    
    if not re.match(r'^[а-яА-ЯёЁa-zA-Z\s]+$', name):
        await message.answer(
            "❌ Имя может содержать только буквы и пробелы.\n"
            "Попробуйте еще раз:"
        )
        return
    
    await state.update_data(username=name)
    await message.answer(
        "Отлично! Теперь введите ваш код клиента:\n"
        "⚠️ Код должен начинаться с 'В+' (например: В+МАКСИМА)\n"
        "(Код клиента вы можете получить в нашей клинике)"
    )
    await state.set_state(RegistrationStates.waiting_for_client_code)

@router.message(RegistrationStates.waiting_for_client_code)
async def process_client_code(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        return
        
    code = message.text.strip().upper()
    
    if len(code) > 11:
        await message.answer(
            "❌ Код клиента слишком длинный. Максимум 11 символов.\n"
            "Попробуйте еще раз:"
        )
        return
    
    if not re.match(r'^[ВC]\+[А-ЯA-Z0-9\-]+$', code):
        await message.answer(
            "❌ Неверный формат кода клиента.\n"
            "Код должен начинаться с 'В+' и содержать только заглавные буквы и цифры.\n"
            "Например: В+МАКСИМА, В+СВКСД1\n"
            "Попробуйте еще раз:"
        )
        return
    
    if len(code) < 3:
        await message.answer(
            "❌ Код клиента слишком короткий.\n"
            "Попробуйте еще раз:"
        )
        return
    
    existing_user = await db.check_client_code_exists(code)
    if existing_user:
        await message.answer(
            "❌ Этот код клиента уже зарегистрирован.\n"
            "Проверьте правильность кода или обратитесь в клинику.\n"
            "Попробуйте еще раз:"
        )
        return
    
    await state.update_data(client_code=code)
    await message.answer(
        "Введите кличку вашего питомца:\n"
        "⚠️ От 2 до 30 символов"
    )
    await state.set_state(RegistrationStates.waiting_for_pet_name)

@router.message(RegistrationStates.waiting_for_pet_name)
async def process_pet_name(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        return
        
    pet_name = message.text.strip()
    
    if len(pet_name) < 2:
        await message.answer(
            "❌ Кличка слишком короткая. Минимум 2 символа.\n"
            "Попробуйте еще раз:"
        )
        return
    
    if len(pet_name) > 30:
        await message.answer(
            "❌ Кличка слишком длинная. Максимум 30 символов.\n"
            "Попробуйте еще раз:"
        )
        return
    
    if not re.match(r'^[а-яА-ЯёЁa-zA-Z0-9\s\-]+$', pet_name):
        await message.answer(
            "❌ Кличка может содержать только буквы, цифры, пробелы и дефис.\n"
            "Попробуйте еще раз:"
        )
        return
    
    await state.update_data(pet_name=pet_name)
    await message.answer(
        "Выберите тип вашего питомца:",
        reply_markup=get_pet_type_kb()
    )
    await state.set_state(RegistrationStates.waiting_for_pet_type)

@router.message(RegistrationStates.waiting_for_pet_type)
async def process_pet_type(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        return
        
    pet_types = ["🐕 Собака", "🐈 Кошка", "🐰 Кролик", "🦜 Птица", "🐹 Грызун", "🦎 Рептилия", "Другое"]
    
    if message.text not in pet_types:
        await message.answer(
            "❌ Пожалуйста, выберите тип питомца из предложенных вариантов",
            reply_markup=get_pet_type_kb()
        )
        return
    
    try:
        data = await state.get_data()
        
        success = await db.add_user(
            telegram_id=message.from_user.id,
            username=data['username'],
            client_code=data['client_code'],
            pet_name=data['pet_name'],
            pet_type=message.text,
            country=data.get('country', 'RU')
        )
        
        if success:
            await message.answer(
                f"✅ Регистрация завершена успешно!\n\n"
                f"🌍 Страна: {data.get('country_name', '🇷🇺 Россия')}\n"
                f"👤 Имя: {data['username']}\n"
                f"🆔 Код клиента: {data['client_code']}\n"
                f"🐾 Питомец: {data['pet_name']}\n"
                f"📝 Тип: {message.text}\n\n"
                "Теперь вы можете пользоваться всеми функциями бота!",
                reply_markup=get_main_menu_kb()
            )
            
            await db.add_request_stat(
                message.from_user.id,
                "registration",
                f"Пользователь зарегистрирован ({data.get('country', 'RU')})"
            )
        else:
            await message.answer(
                "❌ Ошибка регистрации. Произошла техническая ошибка.\n"
                "Попробуйте еще раз: /start",
                reply_markup=ReplyKeyboardRemove()
            )
            
    except Exception as e:
        logger.error(f"Error in registration process: {e}")
        await message.answer(
            "❌ Произошла ошибка при регистрации.\n"
            f"Детали: {str(e)}\n\n"
            "Попробуйте еще раз: /start",
            reply_markup=ReplyKeyboardRemove()
        )
    finally:
        await state.clear()