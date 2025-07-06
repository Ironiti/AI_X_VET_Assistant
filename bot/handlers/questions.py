from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_kb, get_menu_by_role, get_dialog_kb
from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import qwen3_32b_instruct_free as llm
from langchain.schema import SystemMessage, HumanMessage
import json
import re
import base64

questions_router = Router()

class QuestionStates(StatesGroup):
    waiting_for_question = State()
    in_dialog = State()

@questions_router.message(F.text.in_(["❓ Задать вопрос", "🤖 Вопрос нейросети"]))
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

    role = user['role'] if 'role' in user else 'client'
    print(f"[INFO] Resolved role for user {user_id}: {role}")

    await db.clear_buffer(user_id)

    prompt = (
        "🤖 Задайте ваш профессиональный вопрос нейросети.\n\n"
        "Я могу помочь с:\n"
        "• Информацией о лечении животных\n"
        "• Консультациями по симптомам\n"
        "• Рекомендациями по уходу\n"
        "• Ветеринарными препаратами"
        if role == 'staff' else
        "🤖 Задайте ваш профессиональный вопрос нейросети.\n\n"
        "Я могу помочь с:\n"
        "• Информацией о тестах и анализах\n"
        "• Преаналитическими требованиями\n"
        "• Интерпретацией результатов\n"
        "• Общими вопросами по лабораторной диагностике"
    )

    await message.answer(prompt, reply_markup=get_cancel_kb())
    await state.set_state(QuestionStates.waiting_for_question)
    print(f"[INFO] State set to waiting_for_question for user {user_id}")

@questions_router.message(QuestionStates.waiting_for_question)
async def process_question(message: Message, state: FSMContext):
    """Handle user question: update memory, fetch RAG context, ask LLM, update memory."""
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "❌ Отмена":
        await state.clear()
        user = await db.get_user(user_id)
        role = user['role'] if 'role' in user else 'client'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(role))
        print(f"[INFO] User {user_id} cancelled question")
        return

    user = await db.get_user(user_id)
    role = user['role'] if 'role' in user else 'client'
    print(f"[INFO] User {user_id} submitted question: {text} (role={role})")

    # Store the original question in the state for follow-ups
    await state.update_data(original_question=text)

    # Process the question with RAG
    answer = await process_user_question(user_id, text, role, is_new_question=True)
    
    await message.answer(answer, reply_markup=get_dialog_kb())
    await state.set_state(QuestionStates.in_dialog)
    print(f"[INFO] State set to in_dialog for user {user_id}")

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
        role = user['role'] if 'role' in user else 'client'
        await message.answer("Диалог завершен.", reply_markup=get_menu_by_role(role))
        print(f"[INFO] User {user_id} ended dialog")
        return
    
    if text == "🔄 Новый вопрос":
        await db.clear_buffer(user_id)
        await message.answer("Задайте новый вопрос:", reply_markup=get_cancel_kb())
        await state.set_state(QuestionStates.waiting_for_question)
        print(f"[INFO] User {user_id} started new question")
        return

    # Get the original question from the state
    data = await state.get_data()
    original_question = data.get('original_question', '')

    user = await db.get_user(user_id)
    role = user['role'] if 'role' in user else 'client'
    print(f"[INFO] User {user_id} asked follow-up: {text} (role={role})")

    # Process follow-up without RAG (reuse original question context)
    answer = await process_user_question(user_id, text, role, is_new_question=False)
    
    await message.answer(answer, reply_markup=get_dialog_kb())
    print(f"[INFO] Follow-up answer sent to user {user_id}")

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
        rag_hits = processor.search_test(text, top_k=5)

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
        content="Ты — ветеринарный помощник. Используй память и преаналитическую информацию для ответа. Если информации нет - честно скажи об этом. Используй форматирование: **жирный** для важного, _курсив_ для терминов. Будь кратким и профессиональным. Делай приятное оформление для телеграмм. Без использования Markdown"
    )
    user_msg = HumanMessage(
        content=(
            f"{memory_section}"
            f"Контекст преаналитики:\n{rag_context}\n\n"
            f"Вопрос пользователя: {text}\n\n"
            "Ответь на русском языке, кратко и по делу."
        )
    )

    print(f"[INFO] Sending prompt to LLM for user {user_id}")
    response = await llm.agenerate([[system_msg, user_msg]])

    def markdown_to_html(text: str) -> str:
        """Convert basic Markdown to Telegram-compatible HTML."""
        # Bold: **text** -> <b>text</b>
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Italic: _text_ -> <i>text</i>
        text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
        # Code: `text` -> <code>text</code>
        text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
        return text

    answer = response.generations[0][0].text.strip()
    print(f"[INFO] Received LLM answer for user {user_id}")
    answer = markdown_to_html(answer)  # Convert Markdown to HTML
    print(f"[INFO] Converted Markdown to HTML for user {user_id}")
    await db.add_memory(user_id, 'buffer', f"Bot: {answer}")
    print(f"[INFO] Bot response buffered for user {user_id}")

    return answer

