# response_ratings.py
import random
import logging
from typing import Dict, Optional, Tuple
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ResponseRatingManager:
    def __init__(self, db):
        self.feedback_group_link = "https://t.me/+toGEaZZZCYthZGFi"  # ЗАМЕНИТЕ на реальную ссылку
        self.feedback_group_id = -1001234567890  # ЗАМЕНИТЕ на реальный ID группы
        self.db = db
        self._user_cooldown = {}  # Кэш для частых запросов оценки
        self._last_rating_request = {}  # Время последнего запроса оценки для пользователя
    
    async def should_ask_for_rating(self, user_id: int, response_type: str) -> Tuple[bool, str]:
        """Определяет, нужно ли запрашивать оценку"""
        
        # Только для общих вопросов и поиска по названию
        valid_types = {'general', 'name_search'}
        if response_type not in valid_types:
            logger.info(f"[RATING] Skipping rating for response type: {response_type}")
            return False, ""
        
        current_time = datetime.now()
        
        # 1. Проверка частых запросов оценки (не спрашивать слишком часто)
        cooldown_key = f"{user_id}_{response_type}"
        if cooldown_key in self._user_cooldown:
            if current_time < self._user_cooldown[cooldown_key]:
                logger.info(f"[RATING] User {user_id} in cooldown for {response_type}")
                return False, ""
        
        # 2. Проверка времени с последнего запроса оценки (не чаще чем раз в 2 часа)
        last_request_key = f"{user_id}_last_request"
        if last_request_key in self._last_rating_request:
            time_since_last = current_time - self._last_rating_request[last_request_key]
            if time_since_last < timedelta(hours=2):
                logger.info(f"[RATING] User {user_id} was asked recently, skipping")
                return False, ""
        
        # 3. 30% вероятность показа оценки
        rnd = random.random()
        logger.info(f"[RATING] Probability check for user {user_id}: {rnd:.2f}")
        
        if rnd > 0.3:  # 70% случаев НЕ спрашиваем
            logger.info(f"[RATING] Skipping rating by probability for user {user_id}")
            # Ставим кулдаун на 1 час для этого типа ответа
            self._user_cooldown[cooldown_key] = current_time + timedelta(hours=0.05)
            return False, ""
        
        # Генерируем уникальный ID для оценки
        rating_id = f"{user_id}_{int(current_time.timestamp())}"
        
        logger.info(f"[RATING] Will ask for rating from user {user_id}, id: {rating_id}")
        
        # Обновляем время последнего запроса
        self._last_rating_request[last_request_key] = current_time
        # Ставим кулдаун на 4 часа для этого типа ответа
        self._user_cooldown[cooldown_key] = current_time + timedelta(hours=0.05)
            
        return True, rating_id
    
    def create_rating_keyboard(self, rating_id: str) -> InlineKeyboardMarkup:
        """Создает клавиатуру с оценками 1-5"""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="1 ⭐", callback_data=f"rating:{rating_id}:1"),
                    InlineKeyboardButton(text="2 ⭐⭐", callback_data=f"rating:{rating_id}:2"),
                    InlineKeyboardButton(text="3 ⭐⭐⭐", callback_data=f"rating:{rating_id}:3"),
                ],
                [
                    InlineKeyboardButton(text="4 ⭐⭐⭐⭐", callback_data=f"rating:{rating_id}:4"),
                    InlineKeyboardButton(text="5 ⭐⭐⭐⭐⭐", callback_data=f"rating:{rating_id}:5"),
                ]
            ]
        )
    
    def create_feedback_group_keyboard(self) -> InlineKeyboardMarkup:
        """Создает кнопку для перехода в группу обратной связи"""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Предложить улучшение", 
                        url=self.feedback_group_link
                    )
                ]
            ]
        )
    
    async def save_rating(self, user_id: int, rating_id: str, rating: int, 
                         question: str = "", response: str = ""):
        """Сохраняет оценку в базу данных"""
        try:
            await self.db.save_response_rating(
                user_id=user_id,
                chat_history_id=rating_id,
                rating=rating,
                question=question,
                response=response,
                timestamp=datetime.now()
            )
            logger.info(f"[RATING] Saved rating {rating} from user {user_id}")
            
            # После сохранения оценки сбрасываем кэш частых запросов для этого пользователя
            # чтобы можно было снова запросить оценку через 2 часа
            for key in list(self._user_cooldown.keys()):
                if key.startswith(f"{user_id}_"):
                    del self._user_cooldown[key]
                    
        except Exception as e:
            logger.error(f"[RATING] Failed to save rating: {e}")
    
    def prepare_rating_message(self, user_id: int, rating: int, question: str, 
                             response: str, user_name: str = "") -> str:
        """Подготавливает сообщение с оценкой для отправки в группу"""
        rating_stars = "⭐" * rating + "☆" * (5 - rating)
        
        # Обрезаем длинные тексты
        question_preview = question[:200] + "..." if len(question) > 200 else question
        response_preview = response[:300] + "..." if len(response) > 300 else response
        
        message = (
            "📊 <b>Новая оценка ответа бота</b>\n\n"
            f"👤 <b>Пользователь:</b> {user_name or 'Неизвестно'} (ID: {user_id})\n"
            f"📈 <b>Оценка:</b> {rating}/5 {rating_stars}\n"
            f"❓ <b>Вопрос:</b> {question_preview}\n"
            f"💬 <b>Ответ:</b> {response_preview}"
        )
        
        return message
    
    def clear_user_cooldown(self, user_id: int):
        """Очищает кэш для пользователя (например, при сбросе состояния)"""
        for key in list(self._user_cooldown.keys()):
            if key.startswith(f"{user_id}_"):
                del self._user_cooldown[key]
        for key in list(self._last_rating_request.keys()):
            if key.startswith(f"{user_id}_"):
                del self._last_rating_request[key]
    
    @property
    def group_id(self):
        """Возвращает ID группы для обратной связи"""
        return self.feedback_group_id