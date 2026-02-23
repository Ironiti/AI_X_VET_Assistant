"""
Обработчики callback'ов для системы обработки ошибок

Обрабатывает:
- Кнопку "Попробовать снова"
- Кнопку "Связаться со специалистом" (перенаправление на redirect_to_callback)
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.handlers.questions import QuestionStates
from bot.keyboards import get_dialog_kb
import logging

logger = logging.getLogger(__name__)

error_callbacks_router = Router()


@error_callbacks_router.callback_query(F.data == "error_retry")
async def handle_error_retry(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Попробовать снова"
    
    Функционал:
    - Удаляет сообщение об ошибке
    - Возвращает пользователя в режим диалога
    - Предлагает повторить запрос
    """
    await callback.answer("🔄 Попробуйте снова")
    
    try:
        # Удаляем сообщение об ошибке
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"[ERROR_RETRY] Could not delete error message: {e}")
    
    # Получаем данные состояния
    data = await state.get_data()
    
    # Проверяем, есть ли сохраненный предыдущий запрос
    last_question = data.get("last_question")
    previous_query = data.get("original_query")
    
    # Формируем сообщение для пользователя
    if last_question or previous_query:
        query = last_question or previous_query
        message_text = (
            "🔄 <b>Попробуем снова!</b>\n\n"
            f"💬 Ваш предыдущий запрос: <i>{query[:100]}...</i>\n\n"
            "✏️ Введите запрос снова или отредактируйте его:"
        )
    else:
        message_text = (
            "🔄 <b>Готов к новой попытке!</b>\n\n"
            "✏️ Введите ваш запрос:"
        )
    
    # Отправляем сообщение с клавиатурой диалога
    await callback.message.answer(
        message_text,
        parse_mode="HTML",
        reply_markup=get_dialog_kb()
    )
    
    # Устанавливаем состояние ожидания запроса
    await state.set_state(QuestionStates.waiting_for_search_type)
    
    logger.info(f"[ERROR_RETRY] User {callback.from_user.id} initiated retry")


# Обработчик redirect_to_callback уже существует в questions.py,
# поэтому здесь не нужно дублировать его


__all__ = ['error_callbacks_router']
