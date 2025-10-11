"""
Middleware для отслеживания метрик производительности бота
"""
import time
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from datetime import datetime

from src.database.db_init import db

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseMiddleware):
    """
    Middleware для отслеживания времени ответа и других метрик
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Обрабатывает событие и собирает метрики
        """
        # Работаем только с сообщениями
        if not isinstance(event, Message):
            return await handler(event, data)
        
        message: Message = event
        user_id = message.from_user.id
        
        # Проверяем, что пользователь не админ
        try:
            user = await db.get_user(user_id)
            if user and user.get('role') == 'admin':
                # Админы не участвуют в метриках
                return await handler(event, data)
        except Exception as e:
            logger.error(f"[METRICS] Failed to check user role: {e}")
        
        # Засекаем время начала
        start_time = time.time()
        
        # Отслеживаем активность пользователя
        try:
            await db.track_user_activity(user_id)
            await db.update_session_activity(user_id)
        except Exception as e:
            logger.error(f"[METRICS] Failed to track activity: {e}")
        
        # Выполняем обработчик
        try:
            result = await handler(event, data)
            
            # Вычисляем время ответа
            response_time = time.time() - start_time
            
            # Определяем тип запроса
            request_type = self._determine_request_type(message.text)
            
            # Логируем метрику
            try:
                await db.log_request_metric(
                    user_id=user_id,
                    request_type=request_type,
                    query_text=message.text[:500] if message.text else "",
                    response_time=response_time,
                    success=True,
                    has_answer=True
                )
            except Exception as e:
                logger.error(f"[METRICS] Failed to log request metric: {e}")
            
            return result
            
        except Exception as e:
            # В случае ошибки тоже логируем
            response_time = time.time() - start_time
            
            try:
                await db.log_request_metric(
                    user_id=user_id,
                    request_type="error",
                    query_text=message.text[:500] if message.text else "",
                    response_time=response_time,
                    success=False,
                    has_answer=False,
                    error_message=str(e)[:200]
                )
            except Exception as log_error:
                logger.error(f"[METRICS] Failed to log error metric: {log_error}")
            
            raise
    
    def _determine_request_type(self, text: str) -> str:
        """Определяет тип запроса по тексту"""
        if not text:
            return "unknown"
        
        text_lower = text.lower()
        
        # Служебные команды
        if text in ["🔬 Задать вопрос ассистенту", "❌ Завершить диалог", "🔄 Новый вопрос"]:
            return "navigation"
        
        # Проверка на код теста
        import re
        if re.match(r'^[AА][NН]?\d+', text, re.IGNORECASE):
            return "code_search"
        
        if re.match(r'^\d{2,4}[A-ZА-Я]*', text, re.IGNORECASE):
            return "code_search"
        
        # Вопросы
        question_starters = ['как', 'что', 'где', 'когда', 'почему', 'зачем', 'какой', 'можно ли']
        if any(text_lower.startswith(q) for q in question_starters) or text.endswith('?'):
            return "general"
        
        # По умолчанию - поиск по названию
        return "name_search"


class DailyMetricsUpdater:
    """
    Периодическое обновление метрик
    """
    
    def __init__(self):
        self.last_update = datetime.now().date()
    
    async def update_if_needed(self):
        """Обновляет метрики если наступил новый день"""
        today = datetime.now().date()
        
        if today > self.last_update:
            try:
                await db.update_daily_metrics()
                await db.update_quality_metrics()
                await db.update_system_metrics()
                
                self.last_update = today
                logger.info(f"[METRICS] Daily metrics updated for {today}")
            except Exception as e:
                logger.error(f"[METRICS] Failed to update daily metrics: {e}")


# Глобальный экземпляр для обновления метрик
daily_updater = DailyMetricsUpdater()