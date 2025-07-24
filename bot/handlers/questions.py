from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_menu_by_role, get_dialog_kb, get_back_to_menu_kb, get_search_type_kb
from langchain.schema import SystemMessage, HumanMessage, Document
import pytz
import asyncio
import html
import re
from typing import Optional, Dict

from datetime import datetime
from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import qwen3_32b_instruct as llm

# LOADING_GIF_ID = "CgACAgIAAxkBAAMIaGr_qy1Wxaw2VrBrm3dwOAkYji4AAu54AAKmqHlJAtZWBziZvaA2BA"
LOADING_GIF_ID = "CgACAgIAAxkBAAIBFGiBcXtGY7OZvr3-L1dZIBRNqSztAALueAACpqh5Scn4VmIRb4UjNgQ"
questions_router = Router()

class QuestionStates(StatesGroup):
    waiting_for_search_type = State()
    waiting_for_code = State()
    waiting_for_name = State()
    in_dialog = State()

# Словарь аббревиатур для расширения запросов
TEST_ABBREVIATIONS = {
    "ОАК": "общий анализ крови клинический анализ крови гемка гематология",
    "БХ": "биохимический анализ биохимия крови",
    "ОАМ": "общий анализ мочи",
    "СОЭ": "скорость оседания эритроцитов",
    "АЛТ": "аланинаминотрансфераза",
    "АСТ": "аспартатаминотрансфераза",
    "ТТГ": "тиреотропный гормон",
    "Т4": "тироксин",
    "ПЦР": "полимеразная цепная реакция",
    "ИФА": "иммуноферментный анализ",
    "ГЕМКА": "общий анализ крови клинический анализ крови оак гематология",
    "ГЕМАТОЛОГИЯ": "общий анализ крови клинический анализ крови оак гемка",
    "ГЕМАТКА": "общий анализ крови клинический анализ крови оак гемка гематология",
}

def normalize_test_code(text: str) -> str:
    """Normalize test code by converting similar cyrillic chars to latin and uppercase."""
    # Маппинг похожих кириллических букв на латинские
    cyrillic_to_latin = {
        'А': 'A', 'а': 'A',
        'В': 'B', 'в': 'B', 
        'С': 'C', 'с': 'C',
        'Е': 'E', 'е': 'E',
        'Н': 'N', 'н': 'N',  
        'К': 'K', 'к': 'K',
        'М': 'M', 'м': 'M',
        'О': 'O', 'о': 'O',
        'Р': 'P', 'р': 'P',
        'Т': 'T', 'т': 'T',
        'Х': 'X', 'х': 'X',
        'У': 'Y', 'у': 'Y'
    }
    
    # Заменяем кириллические символы на латинские
    result = ''
    for char in text:
        if char in cyrillic_to_latin:
            result += cyrillic_to_latin[char]
        else:
            result += char.upper()
    
    # Добавим логирование для отладки
    print(f"[DEBUG] normalize_test_code: '{text}' -> '{result}'")
    
    return result

def expand_query_with_abbreviations(query: str) -> str:
    """Expand query with known test abbreviations."""
    query_upper = query.upper()
    for abbr, expansion in TEST_ABBREVIATIONS.items():
        if abbr in query_upper:
            return f"{query} {expansion}"
    return query

def safe_html(text: str) -> str:
    """Экранирует HTML символы в тексте"""
    return html.escape(text)

def get_time_based_farewell(user_name: str = None):
    """Возвращает персонализированное прощание в зависимости от времени суток"""
    tz = pytz.timezone('Europe/Minsk')
    current_hour = datetime.now(tz).hour
    
    name_part = f", {user_name}" if user_name and user_name != 'друг' else ""
    
    if 4 <= current_hour < 12:
        return f"Рад был помочь{name_part}! Хорошего утра ☀️"
    elif 12 <= current_hour < 17:
        return f"Рад был помочь{name_part}! Хорошего дня 🤝"
    elif 17 <= current_hour < 22:
        return f"Рад был помочь{name_part}! Хорошего вечера 🌆"
    else:
        return f"Рад был помочь{name_part}! Доброй ночи 🌙"
    
def get_user_first_name(user):
    if not user:
        return 'друг'
    # Совместимость с dict и aiosqlite.Row
    name = user['name'] if 'name' in user.keys() else None
    if not name:
        return 'друг'
    full_name = name.strip()
    name_parts = full_name.split()
    if len(name_parts) >= 2 and ('user_type' in user.keys() and user['user_type'] == 'employee'):
        return name_parts[1]  # Для сотрудников: Фамилия Имя
    return name_parts[0]  # Для клиентов или однословных имен

def format_test_data(metadata: Dict) -> Dict:
    """Extract and format test metadata into standardized dictionary."""
    return {
        'test_code': metadata['test_code'],
        'test_name': metadata['test_name'],
        'container_type': metadata['container_type'],
        'preanalytics': metadata['preanalytics'],
        'storage_temp': metadata['storage_temp'],
        'department': metadata['department']
    }

def format_test_info(test_data: Dict) -> str:
    """Format test information from metadata using HTML tags."""
    return (
        f"<b>Тест: {test_data['test_code']} - {test_data['test_name']}</b>\n\n"
        f"<b>Тип контейнера:</b> {test_data['container_type']}\n"
        f"<b>Преаналитика:</b> {test_data['preanalytics']}\n"
        f"<b>Температура:</b> {test_data['storage_temp']}\n"
        f"<b>Вид исследования:</b> {test_data['department']}\n\n"
    )

async def animate_loading(loading_msg: Message):  # Изменить message на loading_msg
    """Animate loading message (edit text, not caption)."""
    animations = [
        "Обрабатываю ваш запрос...\n⏳ Анализирую данные...",
        "Обрабатываю ваш запрос...\n🔍 Поиск в базе VetUnion...",
        "Обрабатываю ваш запрос...\n🧠 Формирую ответ...",
    ]
    i = 0
    try:
        while True:
            await asyncio.sleep(2)
            i = (i + 1) % len(animations)
            await loading_msg.edit_text(animations[i])  # Теперь правильно
    except (asyncio.CancelledError, Exception):
        pass

async def select_best_match(query: str, docs: list[tuple[Document, float]]) -> list[Document]:
    """Select best matching tests using LLM from multiple options."""
    if len(docs) == 1:
        return [docs[0][0]]
    
    options = "\n".join([
        f"{i}. {doc.metadata['test_name']} ({doc.metadata['test_code']}) - score: {score:.2f}"
        for i, (doc, score) in enumerate(docs, 1)
    ])
    
    prompt = f"""
    Select relevant tests for: "{query}"
    Return ONLY numbers of matching options (1-{len(docs)}) separated by commas.
    
    Options:
    {options}
    """
    
    try:
        response = await llm.agenerate([[SystemMessage(content=prompt)]])
        selected = response.generations[0][0].text.strip()
        
        if not selected:
            return [docs[0][0]]  # Fallback to top result
            
        selected_indices = []
        for num in selected.split(','):
            num = num.strip()
            if num.isdigit() and 1 <= int(num) <= len(docs):
                selected_indices.append(int(num) - 1)
                
        if not selected_indices:
            return [docs[0][0]]
            
        return [docs[i][0] for i in selected_indices]
    except Exception:
        return [docs[0][0]]  # Fallback on error

@questions_router.message(F.text == "🔬 Задать вопрос ассистенту")
async def start_question(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return

    user_name = get_user_first_name(user)  # Добавить эту функцию
    role = user['role'] if 'role' in user else 'staff'
    
    prompt = f"""Привет, {user_name} 👋
    
🔬 Я могу помочь с поиском информации по:
    - всему перечню лабораторных тестов и профилей
    - преаналитическим требованиям
    - типам пробирок/контейнеров
    - условиям хранения/транспортировки проб"""

    await db.clear_buffer(user_id)
    await message.answer(prompt, reply_markup=get_search_type_kb())
    await state.set_state(QuestionStates.waiting_for_search_type)


# Глобальный хендлер для кнопки возврата в меню (работает в любом состоянии)
@questions_router.message(F.text == "🔙 Вернуться в главное меню")
async def handle_back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    role = user['role'] if 'role' in user.keys() else 'staff'
    await message.answer("Операция отменена.", reply_markup=get_menu_by_role(role))
    return

@questions_router.message(QuestionStates.waiting_for_search_type)
async def handle_search_type(message: Message, state: FSMContext):
    """Handle search type selection."""
    text = message.text.strip()
    user_id = message.from_user.id
    
    if text == "🔢 Поиск по коду теста":
        await message.answer("Введите код теста (например, AN5):", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_code)
    elif text == "📝 Поиск по названию":
        await message.answer("Введите название или описание теста:", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_name)
    # обработка возврата в меню удалена, теперь этим занимается глобальный хендлер

@questions_router.message(QuestionStates.waiting_for_code)
async def handle_code_search(message: Message, state: FSMContext):
    """Handle test code search."""
    user_id = message.from_user.id
    # Используем новую функцию нормализации вместо простого upper()
    text = normalize_test_code(message.text.strip())

    try:
        if LOADING_GIF_ID:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
            loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
            animation_task = asyncio.create_task(animate_loading(loading_msg))
        else:
            gif_msg = None
            loading_msg = await message.answer("🔍 Ищем тест...")
            animation_task = None
        
        processor = DataProcessor()
        processor.load_vector_store()
        results = processor.search_test(filter_dict={"test_code": text})
            
            # ... остальной код остается без изменений
        
        if not results:
            raise ValueError("Test not found")
            
        doc = results[0][0]
        test_data = {
            'test_code': doc.metadata['test_code'],
            'test_name': doc.metadata['test_name'],
            'container_type': doc.metadata['container_type'],
            'preanalytics': doc.metadata['preanalytics'],
            'storage_temp': doc.metadata['storage_temp'],
            'department': doc.metadata['department']
        }
        
        if animation_task:
            animation_task.cancel()
        await loading_msg.delete()
        if gif_msg:
            await gif_msg.delete()
        
        await message.answer(format_test_info(test_data), reply_markup=get_dialog_kb(), parse_mode="HTML")
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(current_test=test_data)
        
    except ValueError:
        if 'animation_task' in locals() and animation_task:
            animation_task.cancel()
        if 'loading_msg' in locals():
            await loading_msg.delete()
        if 'gif_msg' in locals() and gif_msg:
            await gif_msg.delete()
        await message.answer("❌ Тест с таким кодом не найден", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
    except Exception as e:
        print(f"[ERROR] Code search failed: {e}")
        if 'animation_task' in locals() and animation_task:
            animation_task.cancel()
        if 'loading_msg' in locals():
            await loading_msg.delete()
        if 'gif_msg' in locals() and gif_msg:
            await gif_msg.delete()
        await message.answer("⚠️ Ошибка при поиске. Попробуйте позже", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)

@questions_router.message(QuestionStates.waiting_for_name)
async def handle_name_search(message: Message, state: FSMContext):
    """Handle test name search using RAG."""
    user_id = message.from_user.id
    text = message.text.strip()

    try:
        if LOADING_GIF_ID:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
            loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
            animation_task = asyncio.create_task(animate_loading(loading_msg))
        else:
            gif_msg = None
            loading_msg = await message.answer("🔍 Ищем тест...")
            animation_task = None
        
        expanded_query = expand_query_with_abbreviations(text)
        processor = DataProcessor()
        processor.load_vector_store()
        
        try:
            rag_hits = processor.search_test(expanded_query, top_k=5)
            
            if not rag_hits:
                raise ValueError("No tests found")
                
            selected_docs = await select_best_match(text, rag_hits)
            
            if animation_task:
                animation_task.cancel()
            await loading_msg.delete()
            if gif_msg:
                await gif_msg.delete()
            
            if len(selected_docs) > 1:
                # Show multiple results
                response = "Найдено несколько подходящих тестов:\n\n"
                for doc in selected_docs:
                    test_data = format_test_data(doc.metadata)
                    response += format_test_info(test_data) + "\n"
                
                await message.answer(response, parse_mode="HTML")
            else:
                # Single result
                test_data = format_test_data(selected_docs[0].metadata)
                await message.answer(
                    format_test_info(test_data),
                    reply_markup=get_dialog_kb(),
                    parse_mode="HTML"
                )
            
            await state.set_state(QuestionStates.in_dialog)
            await state.update_data(current_test=test_data)
            
        except Exception as e:
            print(f"[ERROR] Vector search failed: {e}")
            raise ValueError("Search service unavailable")
            
    except ValueError as e:
        if 'animation_task' in locals() and animation_task:
            animation_task.cancel()
        if 'loading_msg' in locals():
            await loading_msg.delete()
        if 'gif_msg' in locals() and gif_msg:
            await gif_msg.delete()
        await message.answer(f"❌ {str(e)}", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
    except Exception:
        if 'animation_task' in locals() and animation_task:
            animation_task.cancel()
        if 'loading_msg' in locals():
            await loading_msg.delete()
        if 'gif_msg' in locals() and gif_msg:
            await gif_msg.delete()
        await message.answer(
            "⚠️ Ошибка поиска. Попробуйте позже.", 
            reply_markup=get_search_type_kb()
        )
        await state.set_state(QuestionStates.waiting_for_search_type)

@questions_router.message(QuestionStates.in_dialog)
async def handle_dialog(message: Message, state: FSMContext):
    """Handle follow-up questions using LLM."""
    text = message.text.strip()
    user_id = message.from_user.id
    if text == "❌ Завершить диалог":
        await state.clear()
        user = await db.get_user(user_id)
        role = user['role'] if 'role' in user.keys() else 'staff'
        user_name = get_user_first_name(user)
        farewell = get_time_based_farewell(user_name)
        await message.answer(farewell, reply_markup=get_menu_by_role(role))
        return
    if text == "🔄 Новый вопрос":
        await message.answer("Выберите тип поиска:", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
        return
    # обработка возврата в меню удалена, теперь этим занимается глобальный хендлер
    data = await state.get_data()
    test_data = data['current_test'] if 'current_test' in data else None
    if not test_data:
        await message.answer("Контекст потерян. Задайте новый вопрос.", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
        return
    gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
    loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
    animation_task = asyncio.create_task(animate_loading(loading_msg))
    try:
        system_msg = SystemMessage(content=f"""
            You're assisting with questions about lab test:
            Code: {test_data['test_code']}
            Name: {test_data['test_name']}
            Container: {test_data['container_type']}
            Preanalytics: {test_data['preanalytics']}
            
            Answer concisely in Russian using only this information.
        """)
        response = await llm.agenerate([[system_msg, HumanMessage(content=text)]])
        answer = response.generations[0][0].text.strip()
        await loading_msg.edit_text(answer, reply_markup=get_dialog_kb())
    except Exception:
        await loading_msg.edit_text("Ошибка обработки вопроса.", reply_markup=get_dialog_kb())
    finally:
        animation_task.cancel()
        await gif_msg.delete()
