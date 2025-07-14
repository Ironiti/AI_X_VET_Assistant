from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_menu_by_role, get_dialog_kb, get_back_to_menu_kb
from datetime import datetime
from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import qwen3_32b_instruct as llm
from langchain.schema import SystemMessage, HumanMessage
import pytz
import asyncio
import json
import re
import base64
import html

# GIF file_id для анимации загрузки (опционально)
LOADING_GIF_ID = "CgACAgIAAxkBAAMIaGr_qy1Wxaw2VrBrm3dwOAkYji4AAu54AAKmqHlJAtZWBziZvaA2BA"

questions_router = Router()

class QuestionStates(StatesGroup):
    waiting_for_question = State()
    in_dialog = State()
    
def get_time_based_farewell():
    """Возвращает прощание в зависимости от времени суток"""
    tz = pytz.timezone('Europe/Minsk')
    current_hour = datetime.now(tz).hour
    
    if 4 <= current_hour < 12:
        return "Рад был помочь и хорошего утра ☀️"
    elif 12 <= current_hour < 17:
        return "Рад был помочь и хорошего дня 🤝"
    elif 17 <= current_hour < 22:
        return "Рад был помочь и хорошего вечера 🌆"
    else:
        return "Рад был помочь и доброй ночи 🌙"
    
def get_user_first_name(user):
    """Извлекает имя пользователя из полного имени"""
    if not user or not user['name']:
        return 'друг'
    
    full_name = user['name'].strip()
    name_parts = full_name.split()
    
    # Определяем тип пользователя
    # Используем try-except для безопасного доступа к полю
    try:
        user_type = user['user_type']
    except (KeyError, TypeError):
        user_type = ''
    
    if user_type == 'employee' and len(name_parts) >= 2:
        # Для сотрудников: Фамилия Имя -> берем имя
        return name_parts[1]
    elif user_type == 'client' or len(name_parts) == 1:
        # Для клиентов или если только одно слово
        return name_parts[0]
    else:
        # По умолчанию берем первое слово
        return name_parts[0]

@questions_router.message(F.text == "🔬 Задать вопрос ассистенту")
async def start_question(message: Message, state: FSMContext):
    """Begin question flow and reset ephemeral memory buffer."""
    user_id = message.from_user.id
    print(f"[INFO] User {user_id} initiated question flow")

    user = await db.get_user(user_id)
    if not user:
        print(f"[WARN] User {user_id} not registered")
        await message.answer(
            "Для использования этой функции необходимо пройти регистрацию.\n"
            "Используйте команду /start"
        )
        return

    role = user['role'] if user else 'staff'
    user_name = get_user_first_name(user)
    
    print(f"[INFO] Resolved role for user {user_id}: {role}, name: {user_name}")

    await db.clear_buffer(user_id)

    prompt = f"""Привет, {user_name} 👋
    
    🔬 Я могу помочь с поиском информации по:
    - всему перечню лабораторных тестов и профилей (комплексов)
    - преаналитическим требованиям нашей лаборатории
    - типам пробирок/контейнеров и не только 
    - условиям хранения/транспортировки проб"""

    await message.answer(prompt, reply_markup=get_back_to_menu_kb())
    await state.set_state(QuestionStates.waiting_for_question)
    print(f"[INFO] State set to waiting_for_question for user {user_id}")

@questions_router.message(QuestionStates.waiting_for_question)
async def process_question(message: Message, state: FSMContext):
    """Handle user question: update memory, fetch RAG context, ask LLM, update memory."""
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        role = user['role'] if 'role' in user else 'staff'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(role))
        print(f"[INFO] User {user_id} cancelled question")
        return

    user = await db.get_user(user_id)
    role = user['role'] if 'role' in user else 'staff'
    print(f"[INFO] User {user_id} submitted question: {text} (role={role})")

    # Store the original question in the state for follow-ups
    await state.update_data(original_question=text)

    # Отправляем анимированное сообщение о загрузке
    loading_msg = await message.answer_animation(
        animation=LOADING_GIF_ID,
        caption="🤖 Обрабатываю ваш запрос...\n⏳ Анализирую данные..."
    )
    
    # Создаем задачу для анимации загрузки
    animation_task = asyncio.create_task(animate_loading(loading_msg))
    
    try:
        # Process the question with RAG
        answer = await process_user_question(user_id, text, role, is_new_question=True)
        
        # Останавливаем анимацию и удаляем сообщение
        animation_task.cancel()
        try:
            await loading_msg.delete()
        except:
            pass
        
        await message.answer(answer, reply_markup=get_dialog_kb())
        await state.set_state(QuestionStates.in_dialog)
        print(f"[INFO] State set to in_dialog for user {user_id}")
        
    except Exception as e:
        print(f"[ERROR] Error processing question for user {user_id}: {e}")
        animation_task.cancel()
        try:
            await loading_msg.delete()
        except:
            pass
        
        await message.answer(
            "❌ Произошла ошибка при обработке вашего вопроса.\n"
            "Пожалуйста, попробуйте еще раз или обратитесь в поддержку.",
            reply_markup=get_menu_by_role(role)
        )
        await state.clear()

# @questions_router.message(
#     QuestionStates.in_dialog, 
#     F.text.regexp(r'(?i)(фото|покажи|дай).*(контейнер|пробирк|тест|анализ)'),
#     flags={"priority": 10}
# )
# async def send_container_image(message: Message, state: FSMContext):
#     """Send container image when specifically requested."""
#     user_id = message.from_user.id
#     processor = DataProcessor()
#     processor.load_vector_store()
    
#     # Get last question from state
#     data = await state.get_data()
#     question = data.get('original_question', '')
    
#     # Search for relevant test
#     hits = processor.search_test(question, top_k=1)
#     if not hits:
#         await message.answer("Не удалось найти информацию о контейнере.")
#         return
    
#     doc = hits[0][0]  # Get the document from search results
    
#     if 'container_image_base64' not in doc.metadata:
#         await message.answer("Изображение контейнера недоступно для этого теста.")
#         return
    
#     try:
#         image_data = doc.metadata['container_image_base64']
#         if ';base64,' in image_data:
#             image_data = image_data.split(';base64,')[-1]
        
#         image_bytes = base64.b64decode(image_data)
#         await message.answer_photo(
#             BufferedInputFile(image_bytes, "container.jpg"),
#             caption=f"Контейнер для теста: {doc.page_content}"
#         )
#     except Exception as e:
#         await message.answer(f"Ошибка при отправке изображения: {str(e)}")

@questions_router.message(QuestionStates.in_dialog)
async def handle_dialog(message: Message, state: FSMContext):
    """Handle follow-up questions in dialog mode."""
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "❌ Завершить диалог":
        await state.clear()
        user = await db.get_user(user_id)
        role = user['role'] if 'role' in user else 'staff'
        farewell_text = get_time_based_farewell()  # Используем функцию для получения прощания
        await message.answer(farewell_text, reply_markup=get_menu_by_role(role))
        print(f"[INFO] User {user_id} ended dialog")
        return
    
    if text == "🔄 Новый вопрос":
        await db.clear_buffer(user_id)
        await message.answer("Задайте новый вопрос:", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_question)
        print(f"[INFO] User {user_id} started new question")
        return

    # Get the original question from the state
    data = await state.get_data()
    original_question = data.get('original_question', '')

    user = await db.get_user(user_id)
    role = user['role'] if 'role' in user else 'staff'
    print(f"[INFO] User {user_id} asked follow-up: {text} (role={role})")

    # Добавляем анимацию загрузки для follow-up вопросов
    loading_msg = await message.answer_animation(
        animation=LOADING_GIF_ID,
        caption="🤖 Обрабатываю ваш запрос...\n⏳ Анализирую данные..."
    )
    
    animation_task = asyncio.create_task(animate_loading(loading_msg))
    
    try:
        # Process follow-up without RAG (reuse original question context)
        answer = await process_user_question(user_id, text, role, is_new_question=False)
        
        # Останавливаем анимацию и удаляем сообщение
        animation_task.cancel()
        try:
            await loading_msg.delete()
        except:
            pass
        
        await message.answer(answer, reply_markup=get_dialog_kb())
        print(f"[INFO] Follow-up answer sent to user {user_id}")
        
    except Exception as e:
        print(f"[ERROR] Error processing follow-up for user {user_id}: {e}")
        animation_task.cancel()
        try:
            await loading_msg.delete()
        except:
            pass
        
        await message.answer(
            "❌ Произошла ошибка при обработке вашего вопроса.\n"
            "Пожалуйста, попробуйте еще раз.",
            reply_markup=get_dialog_kb()
        )
    
async def animate_loading(message: Message):
    """Анимация загрузки через редактирование подписи к GIF"""
    animations = [
        "🤖 Обрабатываю ваш запрос...\n⏳ Анализирую данные...",
        "🤖 Обрабатываю ваш запрос...\n🔍 Поиск в базе знаний...",
        "🤖 Обрабатываю ваш запрос...\n🧠 Формирую ответ...",
        "🤖 Обрабатываю ваш запрос...\n📝 Подготавливаю результат..."
    ]
    
    i = 0
    try:
        while True:
            await asyncio.sleep(2)
            i = (i + 1) % len(animations)
            await message.edit_caption(caption=animations[i])  # Изменено с edit_text на edit_caption
    except asyncio.CancelledError:
        pass
    except Exception:
        pass

async def process_user_question(user_id: int, text: str, role: str, is_new_question: bool) -> str:
    """Process user question and return AI response."""
    await db.add_request_stat(user_id, "question", text[:200])
    await db.add_memory(user_id, 'buffer', f"User: {text}")

    summary = await db.get_latest_summary(user_id) or ""
    buffer = await db.get_buffer(user_id)

    rag_context = ""
    rag_hits = []  # Initialize empty list for follow-ups
    
    if is_new_question:
        processor = DataProcessor()
        processor.load_vector_store()
        rag_hits = processor.search_test(text, top_k=10)

        rag_blocks = []
        for doc, score in rag_hits:
            clean_meta = {k: v for k, v in doc.metadata.items() if k != 'container_image_base64'}
            meta_json = json.dumps(clean_meta, ensure_ascii=False, sort_keys=True)
            rag_blocks.append(f"Тест: {doc.page_content}\nМетаданные: {meta_json}")
        rag_context = "\n\n---\n\n".join(rag_blocks)

    memory_section = ""
    if summary:
        memory_section += f"Сводка предыдущих сообщений: {summary}\n\n"
    if buffer:
        memory_section += "Последние сообщения:\n" + "\n".join(buffer) + "\n\n"

    system_msg = SystemMessage(
        content="""Ты - ассистент ветеринарной лаборатории VetUnion, помогающий клиентам с информацией об анализах для животных.

ВАЖНЫЕ ПРАВИЛА:

1. ТОЧНОСТЬ ИНФОРМАЦИИ:
- Используй ТОЛЬКО информацию из базы знаний
- НИКОГДА не придумывай коды тестов, названия или параметры
- Если точного соответствия нет - сообщи об этом честно

2. ФОРМАТ ОТВЕТОВ:
- НЕ выводи внутренние коды контейнеров
- Указывай только практическую информацию: тип контейнера, объем, условия взятия
- При неточном запросе предложи уточнить, НЕ предлагая конкретные коды

3. ВЗАИМОДЕЙСТВИЕ:
- Различай благодарности, вопросы и утверждения
- На благодарность отвечай кратко и предлагай дальнейшую помощь
- Сохраняй контекст диалога

4. ПРИ ОТСУТСТВИИ ИНФОРМАЦИИ:
Используй шаблон:
"Не нашел точного соответствия в базе данных. Для подбора анализа уточните:
- Вид животного
- Симптомы или цель исследования
- Предполагаемое направление (биохимия, гематология, инфекции и т.д.)"

5. ЗАПРЕЩЕНО:
- Выдумывать коды тестов
- Ссылаться на несуществующие анализы
- Предлагать конкретные тесты без подтверждения в базе

Не используй HTML/Markdown разметку - только чистый текст."""
    )

    user_msg = HumanMessage(
        content=(
            f"Контекст анализов:\n{rag_context}\n\n"
            f"Запрос: {text}\n\n"
            "ВАЖНО: Используй ТОЛЬКО информацию из предоставленного контекста.\n"
            "Ответ должен быть локаничным и человечным\n"
            "НЕ выдумывай коды тестов, названия или параметры.\n"
            "НЕ показывай внутренние коды контейнеров.\n\n"
            "РАСПОЗНАВАЙ СОКРАЩЕНИЯ:\n"
            "- ОАК = общий анализ крови, клинический анализ крови, гематология\n"
            "- ОАМ = общий анализ мочи, клинический анализ мочи\n"
            "- БХ = биохимия, биохимический анализ\n"
            "- ПЦР = полимеразная цепная реакция\n"
            "- ИФА = иммуноферментный анализ\n"
            "- УЗИ = ультразвуковое исследование\n"
            "Ищи в контексте как по сокращению, так и по полному названию.\n\n"
            "Если в контексте есть точное соответствие запросу - предоставь информацию о:\n"
            "- Название теста\n"
            "- Необходимый материал и объем\n"
            "- Условия взятия и транспортировки\n"
            "- Сроки выполнения\n\n"
            "Если точного соответствия НЕТ:\n"
            "1. Честно сообщи, что не нашел точного соответствия\n"
            "2. НЕ предлагай конкретные коды тестов\n"
            "3. Попроси уточнить:\n"
            "   - Вид животного\n"
            "   - Симптомы или цель исследования\n"
            "   - Направление (биохимия, гематология, инфекции)\n\n"
            "Если это благодарность или подтверждение - ответь кратко и предложи дальнейшую помощь."
        )
    )

    print(f"[INFO] Sending prompt to LLM for user {user_id}")
    response = await llm.agenerate([[system_msg, user_msg]])

    def format_telegram_response(text: str) -> str:
        """Clean response text without any formatting."""
        # Remove all formatting artifacts
        text = re.sub(r'[`*_]', '', text)  # Remove markdown
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
        text = re.sub(r'Ꭵ|Ꭵᴄ', '', text)  # Remove temp markers
        return text.strip()

    answer = response.generations[0][0].text.strip()
    print(f"[INFO] Received LLM answer for user {user_id}")
    answer = format_telegram_response(answer)  # Convert Markdown to HTML
    print(f"[INFO] Converted Markdown to HTML for user {user_id}")
    await db.add_memory(user_id, 'buffer', f"Bot: {answer}")
    print(f"[INFO] Bot response buffered for user {user_id}")

    return answer
