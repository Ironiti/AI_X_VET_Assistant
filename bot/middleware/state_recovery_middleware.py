"""
Middleware для автоматического восстановления состояния пользователя после перезагрузки бота
"""
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


class StateRecoveryMiddleware(BaseMiddleware):
    """
    Middleware для восстановления состояния диалога после перезагрузки бота.
    
    Если пользователь находился в диалоге с ассистентом до перезагрузки,
    показывает информационное сообщение с кнопкой для продолжения поиска.
    """
    
    def __init__(self):
        super().__init__()
        self.recovered_users = set()  # Кеш уже восстановленных пользователей
    
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
        from bot.handlers.questions import QuestionStates
        from src.database.db_init import db
        from bot.handlers.sending_style import get_user_first_name
        
        user_id = event.from_user.id
        state: FSMContext = data.get("state")
        
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
            "❌ Отмена", "🏠 В главное меню", "🔙 Назад к списку вопросов",
            
            # Главное меню
            "🔬 Задать вопрос", "🖼️ Галерея пробирок",
            "📄 Скачать бланки", "📞 Связь с лабораторией",
            "📚 Часто задаваемые вопросы", "📋 Стоп-лист",
            
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
                    # Проверяем, зарегистрирован ли пользователь
                    user = await db.get_user(user_id)
                    
                    if user:
                        # Сохраняем запрос пользователя
                        user_message = event.text.strip()
                        await state.update_data(pending_search_query=user_message)
                        
                        # Восстанавливаем состояние
                        await state.set_state(QuestionStates.waiting_for_search_type)
                        
                        user_name = get_user_first_name(user)
                        
                        # Обрезаем длинный запрос для отображения
                        display_query = user_message if len(user_message) <= 50 else user_message[:47] + "..."
                        
                        from bot.keyboards import get_dialog_kb
                        
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text=f"🔍 Искать: {display_query}",
                                        callback_data="recover_search:execute"
                                    )
                                ]
                            ]
                        )
                        
                        await event.answer(
                            f"👋 С возвращением, {user_name}!\n\n"
                            f"🔄 <b>Бот был перезагружен</b>\n\n"
                            f"📝 Вы написали: <code>{display_query}</code>\n\n"
                            f"💡 Нажмите на кнопку ниже, чтобы выполнить поиск:",
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                        
                        logger.info(f"[STATE_RECOVERY] Showed recovery prompt for user {user_id}, query: {user_message}")
                        
                        # Добавляем в кеш
                        self.recovered_users.add(user_id)
                        
                        # НЕ вызываем handler - пользователь должен нажать кнопку
                        return None
                else:
                    # Состояние есть - добавляем в кеш
                    self.recovered_users.add(user_id)
                
            except Exception as e:
                logger.error(f"[STATE_RECOVERY] Error recovering state for user {user_id}: {e}")
        
        # Продолжаем обработку события
        return await handler(event, data)