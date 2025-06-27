from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Database
from keyboards.reply import get_cancel_kb, get_menu_by_role
from config import DATABASE_PATH
import logging

router = Router()
db = Database(DATABASE_PATH)
logger = logging.getLogger(__name__)

class QuestionStates(StatesGroup):
    waiting_for_question = State()

@router.message(F.text.in_(["❓ Задать вопрос", "🤖 Вопрос нейросети"]))
async def start_question(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer(
            "Для использования этой функции необходимо пройти регистрацию.\n"
            "Используйте команду /start"
        )
        return
    
    role = user['role']
    
    if role == 'staff':
        prompt = (
            "🤖 Задайте ваш вопрос нейросети.\n\n"
            "Я могу помочь с:\n"
            "• Информацией о лечении животных\n"
            "• Консультациями по симптомам\n"
            "• Рекомендациями по уходу\n"
            "• Ветеринарными препаратами"
        )
    else:
        prompt = (
            "❓ Задайте ваш вопрос.\n\n"
            "Я могу помочь с:\n"
            "• Информацией о клинике\n"
            "• Услугами и ценами\n"
            "• Режимом работы\n"
            "• Общими вопросами о питомцах"
        )
    
    await message.answer(prompt, reply_markup=get_cancel_kb())
    await state.set_state(QuestionStates.waiting_for_question)

@router.message(QuestionStates.waiting_for_question)
async def process_question(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        user = await db.get_user(message.from_user.id)
        await message.answer(
            "Операция отменена.", 
            reply_markup=get_menu_by_role(user['role'])
        )
        return
    
    user = await db.get_user(message.from_user.id)
    role = user['role']
    
    # Логируем вопрос
    await db.add_request_stat(
        message.from_user.id,
        "question",
        f"Роль: {role}, Вопрос: {message.text[:200]}..."
    )
    
    # Здесь будет интеграция с нейросетью
    # Пока заглушка с разными ответами для разных ролей
    
    if role == 'staff':
        # Для сотрудников - профессиональный ответ
        answer = (
            "🤖 Ответ нейросети:\n\n"
            "На основе вашего вопроса могу предоставить следующую информацию...\n\n"
            "[Здесь будет подробный ответ от нейросети с профессиональной информацией]"
        )
    else:
        # Для клиентов - общий ответ
        answer = (
            "💬 Ответ:\n\n"
            "Спасибо за ваш вопрос! "
            "[Здесь будет ответ с общей информацией для клиентов]"
        )
    
    await message.answer(answer, reply_markup=get_menu_by_role(role))
    await state.clear()