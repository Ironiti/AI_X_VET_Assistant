"""
Middleware для отслеживания метрик производительности бота
"""
import time
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from datetime import datetime

from src.database.db_init import db

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseMiddleware):
    """
    Middleware для отслеживания времени ответа и других метрик
    Работает как с текстовыми сообщениями, так и с callback queries
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Обрабатывает событие и отслеживает активность пользователя
        """
        # Получаем user_id из события
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        
        # Если не получили user_id - пропускаем
        if not user_id:
            return await handler(event, data)
        
        # Проверяем, что пользователь не админ
        try:
            user = await db.get_user(user_id)
            if user and user.get('role') == 'admin':
                # Админы не участвуют в метриках
                return await handler(event, data)
        except Exception as e:
            logger.error(f"[METRICS] Failed to check user role: {e}")
        
        # Отслеживаем активность пользователя
        # ВАЖНО:
        # - track_user_activity: обновляет user_activity (для DAU)
        # - update_session_activity: создает/обновляет сессии (для метрик времени активности)
        # - log_request_metric: логирует запросы (ТОЛЬКО для валидных запросов в обработчиках)
        try:
            # Отслеживаем активность для DAU (Daily Active Users)
            await db.track_user_activity(user_id)
            
            # Создаем/обновляем сессию при ЛЮБОЙ активности (кнопки, запросы, все)
            # Закрытие неактивных сессий происходит в фоновой задаче (main.py)
            await db.update_session_activity(user_id)
            
            # Логируем тип события для отладки
            event_type = "message" if isinstance(event, Message) else "callback"
            logger.debug(f"[METRICS] Tracked {event_type} activity for user {user_id}")
        except Exception as e:
            logger.error(f"[METRICS] Failed to track activity: {e}")
        
        # ВАЖНО: Логирование в request_metrics происходит ТОЛЬКО в обработчиках
        # для валидных типов запросов: code_search, name_search, general
        # Навигационные действия НЕ логируются в request_metrics
        
        # Выполняем обработчик (метрики запросов логируются в самих обработчиках)
        return await handler(event, data)
    
    def _determine_request_type(self, text: str) -> str:
        """Определяет тип запроса по тексту"""
        if not text:
            return "unknown"
        
        text_lower = text.lower()
        text_stripped = text.strip()
        
        import re
        
        # 1. Команды (НЕ логируются в метрики)
        if text_stripped.startswith('/'):
            return "command"
        
        # 2. Кнопки навигации с эмодзи (логируются но как navigation)
        emoji_buttons = [
            "🔬 Задать вопрос", "❌ Завершить диалог", "🔄 Новый вопрос",
            "🖼 Галерея пробирок и контейнеров", "📄 Ссылки на бланки",
            "🤝 Поддержка"
        ]
        
        for btn in emoji_buttons:
            if text == btn or text_stripped == btn:
                return "navigation"
        
        # 3. Кнопки регистрации (с эмодзи стран/профессий)
        registration_patterns = [
            r'^🇷🇺\s*Россия$',
            r'^🇧🇾\s*Беларусь$',
            r'^🇰🇿\s*Казахстан$',
            r'^🇦🇲\s*Армения$',
            r'^📍\s*.+$',  # Город с эмодзи
            r'^🏙\s*.+$',  # Регион с эмодзи
            r'^🔬\s*Сотрудник VET UNION$',
            r'^🏥\s*Клиент VET UNION$'
        ]
        
        for pattern in registration_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return "navigation"
        
        # 4. Короткие имена при регистрации (одно слово, заглавная буква)
        if len(text_stripped.split()) == 1 and len(text_stripped) < 20:
            # Проверка что это не код теста
            if not re.match(r'^[AА][NН]?\d+', text, re.IGNORECASE) and not re.match(r'^\d+', text):
                # Если первая буква заглавная и не все заглавные - вероятно имя
                if text_stripped[0].isupper() and not text_stripped.isupper():
                    return "navigation"
        
        # 5. Поиск по коду теста (ВАЛИДНЫЙ запрос)
        if re.match(r'^[AА][NН]?\d+[A-ZА-Я]*$', text, re.IGNORECASE):
            return "code_search"
        
        if re.match(r'^\d{2,4}[A-ZА-Я]*$', text, re.IGNORECASE):
            return "code_search"
        
        # 6. Общие вопросы (ВАЛИДНЫЙ запрос)
        question_starters = ['как', 'что', 'где', 'когда', 'почему', 'зачем', 'какой', 'можно ли', 'подскажите', 'скажите']
        if any(text_lower.startswith(q) for q in question_starters) or text.endswith('?'):
            return "general"
        
        # 7. Поиск по названию (ВАЛИДНЫЙ запрос)
        # Все что не команда, не навигация, не вопрос и не код - это поиск по названию
        # Примеры: "Цитология", "фруктозамин", "анализ крови"
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
