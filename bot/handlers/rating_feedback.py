"""
Рабочий модуль для сбора оценок ответов бота.
Готов к использованию - просто подключить роутер в __init__.py
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.handlers.bot_feedback_system import BotFeedbackSystem
from src.database.db_init import db

logger = logging.getLogger(__name__)

# Создаем экземпляр системы обратной связи
feedback_system = BotFeedbackSystem(db)

# Создаем роутер для обработки callback'ов от кнопок оценки
rating_feedback_router = Router(name="rating_feedback")


@rating_feedback_router.callback_query(F.data.startswith("feedback:"))
async def handle_rating_feedback(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик callback'ов от inline-кнопок оценки.
    
    Обрабатывает три типа действий:
    - feedback:positive:{message_id} - положительная оценка (👍 Да)
    - feedback:negative:{message_id} - отрицательная оценка (👎 Нет)
    - feedback:disable:{message_id} - отключение запросов (🔕 Больше не спрашивать)
    """
    try:
        success = await feedback_system.handle_feedback_callback(
            callback=callback,
            state=state
        )
        
        if success:
            logger.info(
                f"[RATING_FEEDBACK] Successfully processed feedback from "
                f"user {callback.from_user.id}"
            )
        else:
            logger.warning(
                f"[RATING_FEEDBACK] Failed to process feedback from "
                f"user {callback.from_user.id}"
            )
            
    except Exception as e:
        logger.error(f"[RATING_FEEDBACK] Error in callback handler: {e}")
        import traceback
        traceback.print_exc()
        
        # Уведомляем пользователя об ошибке
        try:
            await callback.answer(
                "Произошла ошибка. Попробуйте позже.",
                show_alert=True
            )
        except:
            pass


# Экспортируем для использования
__all__ = ['rating_feedback_router', 'feedback_system']
