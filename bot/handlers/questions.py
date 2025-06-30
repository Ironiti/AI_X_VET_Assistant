from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_kb, get_menu_by_role
from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import gemma3_27b_instruct_free as llm
from langchain.schema import SystemMessage, HumanMessage
import json

questions_router = Router()

class QuestionStates(StatesGroup):
    waiting_for_question = State()

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

    # determine role, default to 'client' if missing
    role = user['role'] if 'role' in user.keys() else 'client'
    print(f"[INFO] Resolved role for user {user_id}: {role}")

    # clear only the short-term buffer, keep earlier summary
    await db.clear_buffer(user_id)

    # choose prompt by role
    if role == 'staff':
        prompt = (
            "🤖 Задайте ваш профессиональный вопрос нейросети.\n\n"
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
    print(f"[INFO] State set to waiting_for_question for user {user_id}")

@questions_router.message(QuestionStates.waiting_for_question)
async def process_question(message: Message, state: FSMContext):
    """Handle user question: update memory, fetch RAG context, ask LLM, update memory."""
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "❌ Отмена":
        await state.clear()
        user = await db.get_user(user_id)
        role = user['role'] if 'role' in user.keys() else 'client'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(role))
        print(f"[INFO] User {user_id} cancelled question")
        return

    # resolve role again
    user = await db.get_user(user_id)
    role = user['role'] if 'role' in user.keys() else 'client'
    print(f"[INFO] User {user_id} submitted question: {text} (role={role})")

    # 1) Log and buffer the user question
    await db.add_request_stat(user_id, "question", text[:200])
    await db.add_memory(user_id, 'buffer', f"User: {text}")
    print(f"[INFO] Question logged and buffered for user {user_id}")

    # 2) Retrieve memory summary + buffer
    summary = await db.get_latest_summary(user_id) or ""
    buffer = await db.get_buffer(user_id)
    print(f"[INFO] Retrieved summary and buffer for user {user_id}")

    # 3) Retrieve RAG context
    processor = DataProcessor()
    processor.load_vector_store()
    rag_hits = processor.search_test(text, top_k=5)
    print(f"[INFO] Retrieved {len(rag_hits)} RAG hits for user {user_id}")

    # 4) Build prompt sections
    memory_section = ""
    if summary:
        memory_section += f"Сводка предыдущих сообщений: {summary}\n\n"
    if buffer:
        memory_section += "Последние сообщения:\n" + "\n".join(buffer) + "\n\n"

    rag_blocks = []
    for doc, score in rag_hits:
        meta_json = json.dumps(doc.metadata, ensure_ascii=False, sort_keys=True)
        rag_blocks.append(f"Тест: {doc.page_content}\nМетаданные: {meta_json}")
    rag_context = "\n\n---\n\n".join(rag_blocks)

    system_msg = SystemMessage(
        content="Ты — ветеринарный помощник. Используй память и преаналитическую информацию для ответа."
    )
    user_msg = HumanMessage(
        content=(
            f"{memory_section}"
            f"Контекст преаналитики:\n{rag_context}\n\n"
            f"Вопрос пользователя: {text}\n\n"
            "Ответь на русском языке, кратко и по делу."
        )
    )

    # 5) Call LLM
    print(f"[INFO] Sending prompt to LLM for user {user_id}")
    response = await llm.agenerate([[system_msg, user_msg]])
    answer = response.generations[0][0].text.strip()
    print(f"[INFO] Received LLM answer for user {user_id}")

    # 6) Buffer the bot response
    await db.add_memory(user_id, 'buffer', f"Bot: {answer}")
    print(f"[INFO] Bot response buffered for user {user_id}")

    # 7) Send answer back
    await message.answer(answer, reply_markup=get_menu_by_role(role))
    print(f"[INFO] Answer sent to user {user_id}")

    await state.clear()
    print(f"[INFO] State cleared for user {user_id}")
