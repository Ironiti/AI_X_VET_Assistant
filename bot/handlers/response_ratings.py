# response_ratings.py
import random
import logging
import html
from typing import Dict, Optional, Tuple
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from aiogram.fsm.context import FSMContext


logger = logging.getLogger(__name__)

class ResponseRatingManager:
    def __init__(self, db):
        # ЗАМЕНИТЕ НА РЕАЛЬНЫЕ ДАННЫЕ ВАШЕЙ ГРУППЫ
        self.feedback_group_link = "https://t.me/+EsE7kilfJsk1ODZi" 
        self.feedback_group_id = -1002889617610  
        self.db = db
        self._user_cooldown = {}
        self._last_rating_request = {}


    async def send_rating_to_group(self, bot, user_id: int, rating: int, question: str, 
                                response: str, user_name: str = "", comment: str = ""):
        """Отправляет ПЛОХУЮ оценку (1-3) в группу обратной связи"""
        try:
            # Проверяем что это плохая оценка
            if rating > 3:
                return False
                
            # Проверяем доступ бота к группе
            try:
                chat_member = await bot.get_chat_member(
                    chat_id=self.feedback_group_id,
                    user_id=(await bot.get_me()).id
                )
                
                if chat_member.status not in ["administrator", "creator"]:
                    logger.error("[RATING] Bot is not admin in the group")
                    return False

                    
            except Exception as e:
                logger.error(f"[RATING] Bot access check failed: {e}")
                return False
            
            # Формируем сообщение для группы
            rating_stars = "⭐" * rating + "☆" * (5 - rating)
            
            # ПОЛНОСТЬЮ УБИРАЕМ HTML-ТЕГИ
            clean_question = self.clean_html_text(question)
            clean_response = self.clean_html_text(response)
            clean_comment = self.clean_html_text(comment) if comment else ""
            
            # Обрезаем тексты до разумной длины
            question_preview = clean_question[:500] + "..." if len(clean_question) > 500 else clean_question
            response_preview = clean_response[:800] + "..." if len(clean_response) > 800 else clean_response
            
            # Формируем чистое сообщение без HTML
            message = (
                "🚨 НИЗКАЯ ОЦЕНКА ОТВЕТА\n\n"
                f"👤 Пользователь: {user_name or 'Неизвестно'} (ID: {user_id})\n"
                f"📉 Оценка: {rating}/5 {rating_stars}\n\n"
                f"❓ Вопрос:\n{question_preview}\n\n"
                f"💬 Ответ бота:\n{response_preview}"
            )
            
            if clean_comment:
                comment_preview = clean_comment[:500] + "..." if len(clean_comment) > 500 else clean_comment
                message += f"\n\n💡 Комментарий пользователя:\n{comment_preview}"
            else:
                message += f"\n\n💡 Комментарий: не оставлен"
            
            
            # Отправляем в группу БЕЗ parse_mode=HTML
            await bot.send_message(
                chat_id=self.feedback_group_id,
                text=message,
                parse_mode=None,  # Без HTML-разметки
                disable_web_page_preview=True,
            )
            
            logger.info(f"[RATING] Low rating {rating} from user {user_id} sent to group")
            return True
            
        except Exception as e:
            logger.error(f"[RATING] Failed to send rating to group: {e}")
            return False

    def clean_html_text(self, text: str) -> str:
        """Убирает HTML-теги но сохраняет переносы строк и форматирование"""
        import re
        
        if not text:
            return ""
        
        # Временная замена переносов строк перед удалением тегов
        text = text.replace('\n', '___NEWLINE___')
        
        # Убираем все HTML-теги
        clean_text = re.sub(r'<[^>]+>', '', text)
        
        # Заменяем HTML-сущности
        clean_text = clean_text.replace('&nbsp;', ' ')
        clean_text = clean_text.replace('&amp;', '&')
        clean_text = clean_text.replace('&lt;', '<')
        clean_text = clean_text.replace('&gt;', '>')
        clean_text = clean_text.replace('&quot;', '"')
        clean_text = clean_text.replace('&#39;', "'")
        
        # Восстанавливаем переносы строк
        clean_text = clean_text.replace('___NEWLINE___', '\n')
        
        # Убираем только лишние пробелы (но сохраняем переносы)
        clean_text = re.sub(r'[ \t]+', ' ', clean_text)  # Множественные пробелы и табы
        clean_text = re.sub(r' *\n *', '\n', clean_text)  # Пробелы вокруг переносов
        clean_text = clean_text.strip()
        
        return clean_text

    async def should_ask_for_rating(self, user_id: int, response_type: str, state: FSMContext = None) -> Tuple[bool, str]:
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
            if time_since_last < timedelta(seconds=0):
                logger.info(f"[RATING] User {user_id} was asked recently, skipping")
                return False, ""
        
        # 3. Проверяем, был ли это запрос с подтверждением/уточнением типа
        requires_classification_confirmation = False
        if state:
            try:
                data = await state.get_data()
                
                # Проверяем флаги из состояния
                requires_confirmation = data.get('requires_confirmation', False)
                requires_clarification = data.get('requires_clarification', False)
                
                # Если требовалось подтверждение или уточнение типа - это 100% случай
                requires_classification_confirmation = requires_confirmation or requires_clarification
                
                logger.info(f"[RATING] Classification confirmation required: {requires_classification_confirmation} "
                        f"(confirmation: {requires_confirmation}, clarification: {requires_clarification})")
                
            except Exception as e:
                logger.error(f"[RATING] Error checking classification flags: {e}")
        
        # 4. Определяем вероятность показа оценки
        if requires_classification_confirmation:
            # Для запросов с подтверждением/уточнением типа - всегда спрашиваем оценку (100%)
            should_ask = True
            logger.info(f"[RATING] Always asking for classification confirmation from user {user_id}")
        else:
            # Для остальных случаев - 30% вероятность (оригинальная логика)
            rnd = random.random()
            should_ask = rnd <= 0.3
            logger.info(f"[RATING] Probability check for user {user_id}: {rnd:.2f}, should_ask: {should_ask}")
        
        if not should_ask:
            logger.info(f"[RATING] Skipping rating by probability/logic for user {user_id}")
            # Ставим кулдаун на 1 час для этого типа ответа
            self._user_cooldown[cooldown_key] = current_time + timedelta(seconds=0)
            return False, ""
        
        # Генерируем уникальный ID для оценки
        rating_id = f"{user_id}_{int(current_time.timestamp())}"
        
        logger.info(f"[RATING] Will ask for rating from user {user_id}, id: {rating_id}")
        
        # Обновляем время последнего запроса
        self._last_rating_request[last_request_key] = current_time
        # Ставим кулдаун на 4 часа для этого типа ответа
        self._user_cooldown[cooldown_key] = current_time + timedelta(seconds=0)
            
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