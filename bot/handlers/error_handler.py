"""
Модуль для обработки ошибок и уведомлений администратора

Функции:
- Отправка детальных уведомлений администратору при сбоях
- Логирование всех инцидентов
- Формирование информативных сообщений для пользователей
- Graceful degradation при частичных сбоях
"""

import logging
import traceback
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_API_KEY
from src.database.db_init import db as database
import os

logger = logging.getLogger(__name__)

# ID группы для уведомлений (опционально, можно вынести в .env)
ADMIN_GROUP_ID = os.getenv('ADMIN_GROUP_ID', '')  # ID группы для уведомлений

class ErrorType:
    """Типы ошибок в системе"""
    SERVICE_UNAVAILABLE = "service_unavailable"  # Сервис недоступен
    TIMEOUT = "timeout"  # Таймаут
    API_ERROR = "api_error"  # Ошибка API
    DATABASE_ERROR = "database_error"  # Ошибка БД
    VECTOR_DB_ERROR = "vector_db_error"  # Ошибка векторной БД
    LLM_ERROR = "llm_error"  # Ошибка LLM
    FILE_SYSTEM_ERROR = "file_system_error"  # Ошибка файловой системы
    NETWORK_ERROR = "network_error"  # Сетевая ошибка
    UNKNOWN_ERROR = "unknown_error"  # Неизвестная ошибка


class ErrorNotificationManager:
    """Менеджер для отправки уведомлений об ошибках администратору"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.admin_group_id = int(ADMIN_GROUP_ID) if ADMIN_GROUP_ID and ADMIN_GROUP_ID.strip().isdigit() else None
        self._admin_ids_cache = []
        self._cache_time = 0
        self._cache_ttl = 300  # 5 минут
    
    async def get_admin_ids(self) -> list[int]:
        """
        Получает список ID администраторов из базы данных
        
        Returns:
            list[int]: Список ID администраторов
        """
        import time
        
        # Проверяем кэш
        if self._admin_ids_cache and (time.time() - self._cache_time < self._cache_ttl):
            return self._admin_ids_cache
        
        try:
            # Импортируем aiosqlite для прямого запроса к БД
            import aiosqlite
            
            async with aiosqlite.connect(database.db_path) as conn:
                cursor = await conn.execute(
                    "SELECT telegram_id FROM users WHERE role = 'admin' AND is_active = TRUE"
                )
                rows = await cursor.fetchall()
                admin_ids = [row[0] for row in rows]
                
                # Обновляем кэш
                self._admin_ids_cache = admin_ids
                self._cache_time = time.time()
                
                logger.info(f"[ERROR_NOTIFICATION] Loaded {len(admin_ids)} admin IDs from database")
                return admin_ids
                
        except Exception as e:
            logger.error(f"[ERROR_NOTIFICATION] Failed to get admin IDs from database: {e}")
            # Возвращаем закэшированные ID если есть
            return self._admin_ids_cache
        
    async def send_error_notification(
        self,
        error_type: str,
        error_message: str,
        user_id: Optional[int] = None,
        functionality: Optional[str] = None,
        traceback_text: Optional[str] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ):
        """
        Отправляет детальное уведомление администратору об ошибке
        
        Args:
            error_type: Тип ошибки (из ErrorType)
            error_message: Сообщение об ошибке
            user_id: ID пользователя, у которого возникла ошибка
            functionality: Затронутый функционал
            traceback_text: Стек вызовов
            additional_info: Дополнительная информация
        """
        try:
            error_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            # Формируем сообщение
            notification = f"🚨 <b>ОШИБКА В БОТЕ</b>\n\n"
            notification += f"📅 <b>Время:</b> {error_time}\n"
            notification += f"❌ <b>Тип:</b> {self._get_error_type_emoji(error_type)} {self._format_error_type(error_type)}\n"
            
            if functionality:
                notification += f"⚙️ <b>Функционал:</b> {functionality}\n"
            
            if user_id:
                notification += f"👤 <b>Пользователь:</b> <code>{user_id}</code>\n"
            
            notification += f"\n💬 <b>Сообщение:</b>\n<code>{self._truncate_text(error_message, 500)}</code>\n"
            
            if additional_info:
                notification += f"\n📋 <b>Дополнительно:</b>\n"
                for key, value in additional_info.items():
                    notification += f"• {key}: <code>{self._truncate_text(str(value), 200)}</code>\n"
            
            if traceback_text:
                tb_preview = self._truncate_text(traceback_text, 1000)
                notification += f"\n📚 <b>Стек вызовов:</b>\n<pre>{tb_preview}</pre>\n"
            
            # Добавляем кнопку для просмотра полного лога если есть traceback
            keyboard = None
            if traceback_text and len(traceback_text) > 1000:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📄 Полный стек вызовов",
                                callback_data=f"error_full_trace:{datetime.now().timestamp()}"
                            )
                        ]
                    ]
                )
            
            # Получаем список администраторов из БД
            admin_ids = await self.get_admin_ids()
            
            # Отправляем администраторам
            if self.admin_group_id:
                try:
                    await self.bot.send_message(
                        self.admin_group_id,
                        notification,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    logger.info(f"[ERROR_NOTIFICATION] Sent to admin group {self.admin_group_id}")
                except Exception as e:
                    logger.error(f"[ERROR_NOTIFICATION] Failed to send to group: {e}")
            
            # Отправляем личным администраторам из БД
            if admin_ids:
                for admin_id in admin_ids:
                    try:
                        await self.bot.send_message(
                            admin_id,
                            notification,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                        logger.info(f"[ERROR_NOTIFICATION] Sent to admin {admin_id}")
                    except Exception as e:
                        logger.error(f"[ERROR_NOTIFICATION] Failed to send to admin {admin_id}: {e}")
            else:
                logger.warning("[ERROR_NOTIFICATION] No admin IDs found in database")
            
            # Логируем в файл
            await self._log_error_to_file(
                error_type=error_type,
                error_message=error_message,
                user_id=user_id,
                functionality=functionality,
                traceback_text=traceback_text,
                additional_info=additional_info
            )
            
        except Exception as e:
            logger.error(f"[ERROR_NOTIFICATION] Critical error in notification system: {e}")
    
    def _get_error_type_emoji(self, error_type: str) -> str:
        """Возвращает эмодзи для типа ошибки"""
        emoji_map = {
            ErrorType.SERVICE_UNAVAILABLE: "🔴",
            ErrorType.TIMEOUT: "⏱",
            ErrorType.API_ERROR: "🔌",
            ErrorType.DATABASE_ERROR: "💾",
            ErrorType.VECTOR_DB_ERROR: "🗄",
            ErrorType.LLM_ERROR: "🤖",
            ErrorType.FILE_SYSTEM_ERROR: "📁",
            ErrorType.NETWORK_ERROR: "🌐",
            ErrorType.UNKNOWN_ERROR: "❓"
        }
        return emoji_map.get(error_type, "⚠️")
    
    def _format_error_type(self, error_type: str) -> str:
        """Форматирует тип ошибки для отображения"""
        type_names = {
            ErrorType.SERVICE_UNAVAILABLE: "Сервис недоступен",
            ErrorType.TIMEOUT: "Превышено время ожидания",
            ErrorType.API_ERROR: "Ошибка API",
            ErrorType.DATABASE_ERROR: "Ошибка базы данных",
            ErrorType.VECTOR_DB_ERROR: "Ошибка векторной БД",
            ErrorType.LLM_ERROR: "Ошибка LLM",
            ErrorType.FILE_SYSTEM_ERROR: "Ошибка файловой системы",
            ErrorType.NETWORK_ERROR: "Сетевая ошибка",
            ErrorType.UNKNOWN_ERROR: "Неизвестная ошибка"
        }
        return type_names.get(error_type, error_type)
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """Обрезает текст до указанной длины"""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."
    
    async def _log_error_to_file(
        self,
        error_type: str,
        error_message: str,
        user_id: Optional[int],
        functionality: Optional[str],
        traceback_text: Optional[str],
        additional_info: Optional[Dict[str, Any]]
    ):
        """Логирует ошибку в файл для последующего анализа"""
        try:
            log_file = "logs/errors.log"
            os.makedirs("logs", exist_ok=True)
            
            error_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            log_entry = f"\n{'='*80}\n"
            log_entry += f"[{error_time}] {error_type.upper()}\n"
            log_entry += f"Functionality: {functionality}\n"
            log_entry += f"User ID: {user_id}\n"
            log_entry += f"Error: {error_message}\n"
            
            if additional_info:
                log_entry += f"Additional Info: {additional_info}\n"
            
            if traceback_text:
                log_entry += f"\nTraceback:\n{traceback_text}\n"
            
            log_entry += f"{'='*80}\n"
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            
            logger.info(f"[ERROR_LOG] Error logged to {log_file}")
            
        except Exception as e:
            logger.error(f"[ERROR_LOG] Failed to write error log: {e}")


def get_user_friendly_error_message(
    error_type: str,
    with_retry: bool = True,
    with_contact_support: bool = True,
    custom_message: Optional[str] = None
) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """
    Создает информативное сообщение для пользователя при ошибке
    
    Args:
        error_type: Тип ошибки
        with_retry: Добавить кнопку "Попробовать снова"
        with_contact_support: Добавить кнопку связи с поддержкой
        custom_message: Кастомное сообщение
    
    Returns:
        tuple: (текст сообщения, клавиатура)
    """
    
    # Базовые сообщения для разных типов ошибок
    error_messages = {
        ErrorType.SERVICE_UNAVAILABLE: (
            "🔧 <b>Временные технические работы</b>\n\n"
            "Ассистент временно недоступен. Мы уже работаем над решением.\n\n"
            "⏰ Обычно это занимает несколько минут.\n"
            "Пожалуйста, попробуйте позже."
        ),
        ErrorType.TIMEOUT: (
            "⏱ <b>Превышено время ожидания</b>\n\n"
            "Запрос обрабатывается слишком долго. Это может быть связано с высокой нагрузкой.\n\n"
            "💡 Попробуйте:\n"
            "• Упростить запрос\n"
            "• Повторить через несколько секунд"
        ),
        ErrorType.API_ERROR: (
            "🔌 <b>Временные трудности с подключением</b>\n\n"
            "Возникла ошибка при обработке запроса. Мы уже получили уведомление и работаем над исправлением.\n\n"
            "⌛ Пожалуйста, попробуйте позже."
        ),
        ErrorType.DATABASE_ERROR: (
            "💾 <b>Временные технические проблемы</b>\n\n"
            "Возникла временная проблема с доступом к данным. Наша команда уже уведомлена.\n\n"
            "🔄 Попробуйте повторить операцию через минуту."
        ),
        ErrorType.VECTOR_DB_ERROR: (
            "🗄 <b>Проблема с поиском</b>\n\n"
            "Временно недоступна функция поиска. Мы работаем над восстановлением.\n\n"
            "📞 Вы можете связаться с нашим специалистом напрямую."
        ),
        ErrorType.LLM_ERROR: (
            "🤖 <b>Проблема с обработкой запроса</b>\n\n"
            "AI-система временно недоступна или перегружена.\n\n"
            "💡 Попробуйте:\n"
            "• Переформулировать вопрос\n"
            "• Использовать поиск по коду теста\n"
            "• Связаться со специалистом"
        ),
        ErrorType.NETWORK_ERROR: (
            "🌐 <b>Проблема с сетевым подключением</b>\n\n"
            "Возникла проблема с сетью. Пожалуйста, проверьте ваше интернет-соединение.\n\n"
            "🔄 Попробуйте повторить запрос."
        ),
        ErrorType.UNKNOWN_ERROR: (
            "⚠️ <b>Непредвиденная ошибка</b>\n\n"
            "Произошла непредвиденная ошибка. Наша команда уже получила уведомление.\n\n"
            "🙏 Приносим извинения за неудобства."
        )
    }
    
    # Выбираем сообщение
    message = custom_message if custom_message else error_messages.get(
        error_type,
        error_messages[ErrorType.UNKNOWN_ERROR]
    )
    
    # Создаем клавиатуру
    buttons = []
    
    if with_retry:
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Попробовать снова",
                callback_data="error_retry"
            )
        ])
    
    if with_contact_support:
        buttons.append([
            InlineKeyboardButton(
                text="📞 Связаться со специалистом",
                callback_data="redirect_to_callback"
            )
        ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    
    return message, keyboard


async def handle_error_gracefully(
    error: Exception,
    bot: Bot,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    functionality: str = "Unknown",
    additional_info: Optional[Dict[str, Any]] = None
) -> tuple[str, str]:
    """
    Обрабатывает ошибку с уведомлением админа и возвратом user-friendly сообщения
    
    Args:
        error: Исключение
        bot: Экземпляр бота
        user_id: ID пользователя
        chat_id: ID чата для отправки сообщения пользователю
        functionality: Название функционала, где произошла ошибка
        additional_info: Дополнительная информация
    
    Returns:
        tuple: (error_type, error_message)
    """
    
    # Определ��ем тип ошибки
    error_type = _detect_error_type(error)
    error_message = str(error)
    traceback_text = traceback.format_exc()
    
    # Логируем
    logger.error(f"[ERROR_HANDLER] {error_type} in {functionality}: {error_message}")
    logger.error(f"[ERROR_HANDLER] Traceback:\n{traceback_text}")
    
    # Отправляем уведомление админу
    notification_manager = ErrorNotificationManager(bot)
    try:
        await notification_manager.send_error_notification(
            error_type=error_type,
            error_message=error_message,
            user_id=user_id,
            functionality=functionality,
            traceback_text=traceback_text,
            additional_info=additional_info
        )
    except Exception as notify_error:
        logger.error(f"[ERROR_HANDLER] Failed to send admin notification: {notify_error}")
    
    # Формируем сообщение для пользователя
    user_message, keyboard = get_user_friendly_error_message(
        error_type=error_type,
        with_retry=True,
        with_contact_support=True
    )
    
    # Отправляем сообщение пользователю если указан chat_id
    if chat_id:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=user_message,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception as send_error:
            logger.error(f"[ERROR_HANDLER] Failed to send user message: {send_error}")
    
    return error_type, error_message


def _detect_error_type(error: Exception) -> str:
    """Определяет тип ошибки на основе исключения"""
    error_type_str = str(type(error).__name__).lower()
    error_message = str(error).lower()
    
    # Таймауты
    if 'timeout' in error_type_str or 'timeout' in error_message:
        return ErrorType.TIMEOUT
    
    # API ошибки
    if any(x in error_message for x in ['api', 'request', 'response', 'status code']):
        return ErrorType.API_ERROR
    
    # БД ошибки
    if any(x in error_message for x in ['database', 'sql', 'connection', 'sqlite', 'postgres']):
        return ErrorType.DATABASE_ERROR
    
    # Векторная БД
    if any(x in error_message for x in ['chroma', 'vector', 'embedding']):
        return ErrorType.VECTOR_DB_ERROR
    
    # LLM ошибки
    if any(x in error_message for x in ['llm', 'model', 'gemini', 'openai', 'anthropic']):
        return ErrorType.LLM_ERROR
    
    # Файловая система
    if any(x in error_type_str for x in ['file', 'io', 'permission']):
        return ErrorType.FILE_SYSTEM_ERROR
    
    # Сетевые ошибки
    if any(x in error_type_str for x in ['connection', 'network', 'http']):
        return ErrorType.NETWORK_ERROR
    
    # Неизвестно
    return ErrorType.UNKNOWN_ERROR


# Декоратор для автоматической обработки ошибок
def with_error_handling(functionality: str):
    """
    Декоратор для автоматической обработки ошибок в хендлерах
    
    Usage:
        @with_error_handling("code_search")
        async def handle_code_search(message: Message, state: FSMContext):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Извлекаем bot и message из аргументов
                message = args[0] if len(args) > 0 else None
                bot = message.bot if message and hasattr(message, 'bot') else None
                user_id = message.from_user.id if message and hasattr(message, 'from_user') else None
                chat_id = message.chat.id if message and hasattr(message, 'chat') else None
                
                if bot:
                    await handle_error_gracefully(
                        error=e,
                        bot=bot,
                        user_id=user_id,
                        chat_id=chat_id,
                        functionality=functionality
                    )
                else:
                    logger.error(f"[ERROR_HANDLER] No bot instance in {functionality}: {e}")
                    raise
        
        return wrapper
    return decorator


__all__ = [
    'ErrorType',
    'ErrorNotificationManager',
    'get_user_friendly_error_message',
    'handle_error_gracefully',
    'with_error_handling'
]
