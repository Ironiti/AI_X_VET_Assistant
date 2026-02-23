# bot_feedback_system.py
"""
Система запроса обратной связи от пользователей после каждого ответа бота.
Позволяет собирать оценки качества ответов для последующего анализа.
"""

import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


class BotFeedbackSystem:
    """
    Система сбора обратной связи от пользователей.
    
    Функционал:
    - Запрос оценки после ответа бота (Да/Нет/Больше не спрашивать)
    - Сохранение оценок в БД с временными метками
    - Управление настройками пользователей
    - Анализ метрик качества ответов
    """
    
    def __init__(self, db):
        """
        Инициализация системы обратной связи
        
        Args:
            db: Экземпляр класса Database для работы с БД
        """
        self.db = db
        self._cooldown_cache = {}  # Кэш для предотвращения частых запросов
        self._cooldown_period = 0  # ОТКЛЮЧЕН: показывать после каждого ответа
        
        logger.info("[FEEDBACK] Bot Feedback System initialized with NO cooldown (always show)")
    
    async def should_request_feedback(
        self,
        user_id: int,
        response_type: str = "general"
    ) -> bool:
        """
        Определяет, нужно ли запрашивать оценку у пользователя
        
        Args:
            user_id: ID пользователя
            response_type: Тип ответа (general, code_search, name_search)
            
        Returns:
            bool: True если нужно запросить, False если нет
        """
        try:
            # 1. Проверяем, не отключил ли пользователь запросы оценки
            is_enabled = await self.db.is_user_rating_enabled(user_id)
            if not is_enabled:
                logger.info(f"[FEEDBACK] User {user_id} has disabled ratings")
                return False
            
            # 2. Проверяем кулдаун (не спрашиваем слишком часто)
            current_time = datetime.now()
            cooldown_key = f"{user_id}_{response_type}"
            
            if cooldown_key in self._cooldown_cache:
                last_request_time = self._cooldown_cache[cooldown_key]
                time_diff = (current_time - last_request_time).total_seconds()
                
                if time_diff < self._cooldown_period:
                    logger.info(
                        f"[FEEDBACK] User {user_id} in cooldown "
                        f"({int(time_diff)}s / {self._cooldown_period}s)"
                    )
                    return False
            
            # 3. Запрашиваем оценку (можно добавить вероятностную логику)
            # Для простоты запрашиваем всегда, когда прошло достаточно времени
            logger.info(f"[FEEDBACK] Will request feedback from user {user_id}")
            
            # Обновляем время последнего запроса
            self._cooldown_cache[cooldown_key] = current_time
            
            return True
            
        except Exception as e:
            logger.error(f"[FEEDBACK] Error in should_request_feedback: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_feedback_keyboard(self, message_id: int) -> InlineKeyboardMarkup:
        """
        Создает inline-клавиатуру для запроса оценки
        
        Args:
            message_id: ID сообщения для идентификации
            
        Returns:
            InlineKeyboardMarkup: Клавиатура с тремя кнопками
        """
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👍 Да",
                        callback_data=f"feedback:positive:{message_id}"
                    ),
                    InlineKeyboardButton(
                        text="👎 Нет",
                        callback_data=f"feedback:negative:{message_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔕 Больше не спрашивать",
                        callback_data=f"feedback:disable:{message_id}"
                    )
                ]
            ]
        )
    
    async def handle_feedback_callback(
        self,
        callback: CallbackQuery,
        state: FSMContext = None
    ) -> bool:
        """
        Обработчик callback'ов от кнопок оценки
        
        Args:
            callback: Объект CallbackQuery от aiogram
            state: FSMContext для получения данных о вопросе/ответе
            
        Returns:
            bool: True если успешно обработано
        """
        try:
            # Парсим callback_data: "feedback:type:message_id"
            _, rating_type, message_id_str = callback.data.split(":", 2)
            message_id = int(message_id_str)
            user_id = callback.from_user.id
            
            logger.info(
                f"[FEEDBACK] Processing {rating_type} from user {user_id}, "
                f"message {message_id}"
            )
            
            # Получаем данные о вопросе и ответе из state (если доступны)
            question = ""
            bot_response = ""
            
            if state:
                try:
                    data = await state.get_data()
                    question = data.get('last_question', '')
                    bot_response = data.get('last_bot_response', '')
                except Exception as e:
                    logger.warning(f"[FEEDBACK] Could not get state data: {e}")
            
            # Обрабатываем разные типы оценки
            if rating_type == "disable":
                # Пользователь отключает запросы оценки
                success = await self.db.disable_user_ratings(user_id)
                
                if success:
                    await callback.message.edit_text(
                        "✅ Запросы оценки отключены. Вы всегда можете включить их "
                        "снова, обратившись к администратору.",
                        reply_markup=None
                    )
                    await callback.answer("Запросы оценки отключены")
                else:
                    await callback.answer(
                        "❌ Ошибка при отключении запросов",
                        show_alert=True
                    )
                return success
                
            elif rating_type in ["positive", "negative"]:
                # Сохраняем оценку
                success = await self.db.save_bot_response_rating(
                    user_id=user_id,
                    message_id=message_id,
                    rating_type=rating_type,
                    question=question,
                    bot_response=bot_response
                )
                
                if success:
                    # Формируем благодарственное сообщение
                    if rating_type == "positive":
                        thank_you_text = "✅ Спасибо за положительную оценку!"
                    else:
                        thank_you_text = (
                            "📝 Спасибо за обратную связь! "
                            "Мы работаем над улучшением качества ответов."
                        )
                    
                    # Редактируем сообщение, убирая кнопки
                    await callback.message.edit_text(
                        thank_you_text,
                        reply_markup=None
                    )
                    
                    await callback.answer("Оценка сохранена")
                else:
                    await callback.answer(
                        "❌ Ошибка при сохранении оценки",
                        show_alert=True
                    )
                
                return success
            
            else:
                logger.error(f"[FEEDBACK] Unknown rating type: {rating_type}")
                await callback.answer("Неизвестный тип оценки")
                return False
                
        except ValueError as e:
            logger.error(f"[FEEDBACK] Invalid callback data format: {e}")
            await callback.answer("Ошибка формата данных")
            return False
        except Exception as e:
            logger.error(f"[FEEDBACK] Error handling feedback callback: {e}")
            import traceback
            traceback.print_exc()
            await callback.answer("Произошла ошибка")
            return False
    
    async def send_feedback_request(
        self,
        message: Message,
        bot_response_message_id: int,
        state: FSMContext = None
    ) -> Optional[Message]:
        """
        Отправляет запрос оценки пользователю
        
        Args:
            message: Исходное сообщение пользователя
            bot_response_message_id: ID сообщения с ответом бота
            state: FSMContext для сохранения данных
            
        Returns:
            Message: Отправленное сообщение с запросом или None
        """
        try:
            user_id = message.from_user.id
            
            # Проверяем, нужно ли запрашивать оценку
            should_request = await self.should_request_feedback(user_id)
            
            if not should_request:
                return None
            
            # Сохраняем данные в state для последующего использования
            if state:
                try:
                    await state.update_data(
                        last_question=message.text or "",
                        last_bot_response_message_id=bot_response_message_id
                    )
                except Exception as e:
                    logger.warning(f"[FEEDBACK] Could not save to state: {e}")
            
            # Формируем и отправляем запрос оценки
            feedback_text = "❓ Был ли мой ответ полезен?"
            
            keyboard = self.create_feedback_keyboard(bot_response_message_id)
            
            feedback_message = await message.answer(
                feedback_text,
                reply_markup=keyboard
            )

            # ВАЖНО: логируем факт показа формы оценки.
            # Это используется как знаменатель для метрики "Коэффициент отклика"
            # (сколько раз пользователям реально показали кнопки оценки).
            try:
                await self.db.log_feedback_prompt(
                    user_id=user_id,
                    bot_response_message_id=bot_response_message_id,
                    prompt_message_id=feedback_message.message_id,
                    timestamp=datetime.now()
                )
            except Exception as e:
                logger.warning(f"[FEEDBACK] Could not log feedback prompt: {e}")
            
            logger.info(
                f"[FEEDBACK] Sent feedback request to user {user_id}, "
                f"message_id {feedback_message.message_id}"
            )
            
            return feedback_message
            
        except Exception as e:
            logger.error(f"[FEEDBACK] Error sending feedback request: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_user_feedback_stats(self, user_id: int) -> dict:
        """
        Получает статистику оценок конкретного пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: Статистика оценок
        """
        try:
            history = await self.db.get_user_rating_history(user_id, limit=100)
            
            if not history:
                return {
                    'total': 0,
                    'positive': 0,
                    'negative': 0,
                    'declined': 0
                }
            
            stats = {
                'total': len(history),
                'positive': sum(1 for r in history if r['rating_type'] == 'positive'),
                'negative': sum(1 for r in history if r['rating_type'] == 'negative'),
                'declined': sum(1 for r in history if r['rating_type'] == 'declined')
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"[FEEDBACK] Error getting user stats: {e}")
            return {'total': 0, 'positive': 0, 'negative': 0, 'declined': 0}
    
    def clear_user_cooldown(self, user_id: int):
        """
        Очищает кулдаун для пользователя (например, при сбросе состояния)
        
        Args:
            user_id: ID пользователя
        """
        keys_to_remove = [k for k in self._cooldown_cache.keys() if k.startswith(f"{user_id}_")]
        for key in keys_to_remove:
            del self._cooldown_cache[key]
        
        logger.info(f"[FEEDBACK] Cleared cooldown for user {user_id}")
    
    async def get_overall_stats(self, days: int = 30) -> dict:
        """
        Получает общую статистику системы оценок
        
        Args:
            days: Период для анализа в днях
            
        Returns:
            dict: Общая статистика
        """
        try:
            stats = await self.db.get_bot_rating_stats(days)
            return stats or {}
        except Exception as e:
            logger.error(f"[FEEDBACK] Error getting overall stats: {e}")
            return {}
