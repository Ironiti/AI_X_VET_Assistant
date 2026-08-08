"""Silent fallback for users whose legacy in-memory state was lost."""
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.fsm.state import State
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


class StateRecoveryMiddleware(BaseMiddleware):
    """Route legacy post-restart text into search without a technical prompt."""
    
    def __init__(self, database=None, recovery_state=None):
        super().__init__()
        self.database = database
        self.recovery_state = recovery_state
        self.recovered_users = set()
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """
        Обработчик middleware
        
        Args:
            handler: Следующий обработчик в цепочке
            event: Событие (Message или CallbackQuery)
            data: Дополнительные данные
        """
        if self.recovery_state is None:
            from bot.handlers.questions import QuestionStates
            recovery_state = QuestionStates.waiting_for_search_type
        else:
            recovery_state = self.recovery_state

        if self.database is None:
            from src.database.db_init import db
            database = db
        else:
            database = self.database
        
        if event.from_user is None:
            return await handler(event, data)

        user_id = event.from_user.id
        state: FSMContext = data.get("state")

        if state is None:
            return await handler(event, data)
        
        # Пропускаем callback для восстановления поиска
        if isinstance(event, CallbackQuery) and event.data == "recover_search:execute":
            return await handler(event, data)
        
        # Пропускаем, если это команда /start - регистрация сама установит нужное состояние
        if isinstance(event, Message) and event.text and event.text.startswith('/start'):
            return await handler(event, data)
        
        # Список всех кнопок меню, которые НЕ должны триггерить восстановление
        menu_buttons = {
            # Служебные кнопки
            "🔙 Вернуться в главное меню", "❌ Завершить диалог", "🔙 Назад",
            "❌ Отмена", "🏠 В главное меню", "🔙 Назад к списку вопросов", "❌ Выйти из опроса",
            "✅ Отправить", "🗑 Очистить", "↩️ Удалить файл",
            
            # Главное меню
            "🔬 Задать вопрос", "🔬 Вопрос по преаналитике", "🔬 Преаналитика",
            "🧪 Запрос по результатам", "🧪 Результаты",
            "🖼️ Галерея пробирок", "🖼️ Галерея пробирок и контейнеров",
            "🖼 Галерея пробирок и контейнеров", "📷 Пробирки",
            "📄 Скачать бланки", "📄 Ссылки на бланки", "📄 Бланки",
            "📞 Связь с лабораторией",
            "📞 Заказать звонок", "💬 Жалобы и предложения", "💬 Обратная связь",
            "📚 Часто задаваемые вопросы", "📋 Стоп-лист",
            "📋 Актуальный стоп-лист",
            
            # Админ меню
            "📊 Статистика", "📈 Экспорт метрик", "📥 Выгрузка в Excel",
            "👥 Пользователи", "🔐 Создать код", "🔑 Активировать код",
            "📋 Все обращения", "📋 Опросы", "📢 Рассылка",
            "🎨 Управление контентом", "🔧 Управление системой", "⚙️ Управление стоп-листом",
            
            # Контент и связь
            "⚙️ Управление галереей", "⚙️ Управление бланками",
            "📞 Заказать звонок", "💡 Предложение/жалоба",
            "💡 Предложение", "⚠️ Жалоба",
            
            # Excel выгрузка
            "📊 Полная выгрузка", "👥 Только пользователи", "❓ Только вопросы",
            "💬 История общения с ботом", "📞 Только звонки", "💡 Только обратная связь",
            
            # Рассылка
            "📢 Всем пользователям", "👨‍⚕️ Только клиентам", "🔬 Только сотрудникам",
            
            # Система
            "🔄 Обновить векторную БД", "🗑️ Очистить старые логи",
            "📊 Системная информация", "🧪 Управление фото контейнеров",
            
            # FAQ
            "🔍 Поиск по базе знаний", "📋 Показать все вопросы",
            
            # Поиск (старая клавиатура)
            "🔢 Поиск по коду теста", "📝 Поиск по названию", "❓ Общий вопрос",
            
            # Подтверждение
            "✅ Да", "❌ Нет",
            
            # Телефон
            "📱 Поделиться номером"
        }
        
        # Пропускаем кнопки меню
        if isinstance(event, Message) and event.text in menu_buttons:
            return await handler(event, data)
        
        # Проверяем состояние только для сообщений и только один раз за сессию
        if isinstance(event, Message) and user_id not in self.recovered_users and state:
            try:
                # Получаем текущее состояние
                current_state = await state.get_state()
                
                # Если состояние отсутствует (None) - бот был перезагружен
                if current_state is None:
                    if not event.text:
                        return await handler(event, data)

                    # Проверяем, зарегистрирован ли пользователь
                    user = await database.get_user(user_id)
                    
                    if user:
                        await state.set_state(recovery_state)
                        data["raw_state"] = (
                            recovery_state.state
                            if isinstance(recovery_state, State)
                            else recovery_state
                        )
                        self.recovered_users.add(user_id)
                        logger.info(
                            "[STATE_RECOVERY] Silently restored search state for user %s",
                            user_id,
                        )
                else:
                    # Состояние есть - добавляем в кеш
                    self.recovered_users.add(user_id)
                
            except Exception as e:
                logger.error(f"[STATE_RECOVERY] Error recovering state for user {user_id}: {e}")
        
        # Продолжаем обработку события
        return await handler(event, data)
