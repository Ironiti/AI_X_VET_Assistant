"""
Middleware для глобальной обработки ошибок

Перехватывает все необработанные исключения и:
- Отправляет уведомления администратору
- Показывает пользователю информативное сообщение
- Логирует инциденты для анализа
- Обеспечивает graceful degradation
"""

import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from bot.handlers.error_handler import (
    handle_error_gracefully,
    ErrorNotificationManager
)

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
    """
    Middleware для глобальной обработки ошибок
    
    Перехватывает все необработанные исключения в хендлерах
    и обеспечивает корректную обработку с уведомлениями
    """
    
    def __init__(self):
        super().__init__()
        logger.info("[ERROR_MIDDLEWARE] Initialized")
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Обработчик middleware
        
        Args:
            handler: Следующий обработчик в цепочке
            event: Событие (Message, CallbackQuery, и т.д.)
            data: Данные контекста
        """
        try:
            # Пытаемся выполнить хендлер
            return await handler(event, data)
            
        except Exception as error:
            # Извлекаем информацию о событии
            user_id = None
            chat_id = None
            functionality = "unknown"
            bot = data.get('bot')
            
            # Определяем тип события и извлекаем данные
            if isinstance(event, Message):
                user_id = event.from_user.id if event.from_user else None
                chat_id = event.chat.id if event.chat else None
                functionality = f"message_handler: {event.text[:50] if event.text else 'non-text'}"
                
            elif isinstance(event, CallbackQuery):
                user_id = event.from_user.id if event.from_user else None
                chat_id = event.message.chat.id if event.message and event.message.chat else None
                functionality = f"callback_handler: {event.data}"
            
            # Дополнительная информация для логирования
            additional_info = {
                "event_type": type(event).__name__,
                "user_id": user_id,
                "chat_id": chat_id,
            }
            
            # Если это Message, добавляем информацию о сообщении
            if isinstance(event, Message):
                additional_info.update({
                    "message_id": event.message_id,
                    "text_preview": event.text[:100] if event.text else None,
                    "content_type": event.content_type if hasattr(event, 'content_type') else None
                })
            
            # Если это CallbackQuery, добавляем данные callback
            elif isinstance(event, CallbackQuery):
                additional_info.update({
                    "callback_data": event.data,
                    "message_id": event.message.message_id if event.message else None
                })
            
            # Логируем ошибку
            logger.error(
                f"[ERROR_MIDDLEWARE] Unhandled error in {functionality}: {error}",
                exc_info=True,
                extra=additional_info
            )
            
            # Обрабатываем ошибку и отправляем уведомления
            if bot:
                try:
                    await handle_error_gracefully(
                        error=error,
                        bot=bot,
                        user_id=user_id,
                        chat_id=chat_id,
                        functionality=functionality,
                        additional_info=additional_info
                    )
                except Exception as handle_error:
                    # Если даже обработка ошибки упала - логируем критическую ошибку
                    logger.critical(
                        f"[ERROR_MIDDLEWARE] Critical: Error handler itself failed: {handle_error}",
                        exc_info=True
                    )
                    
                    # Пытаемся хотя бы ответить пользователю
                    if chat_id:
                        try:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    "⚠️ Произошла критическая ошибка.\n"
                                    "Пожалуйста, попробуйте позже или свяжитесь с поддержкой."
                                )
                            )
                        except Exception:
                            pass  # Если и это не удалось - больше ничего не можем сделать
            
            # Важно: не пробрасываем исключение дальше,
            # чтобы бот продолжал работать для других пользователей
            return None


class CriticalErrorMiddleware(BaseMiddleware):
    """
    Middleware для обработки критических ошибок на уровне диспетчера
    
    Это последний уровень защиты - если ошибка прошла через все другие middleware
    """
    
    def __init__(self):
        super().__init__()
        logger.info("[CRITICAL_ERROR_MIDDLEWARE] Initialized")
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as error:
            logger.critical(
                f"[CRITICAL_ERROR_MIDDLEWARE] Unhandled critical error: {error}",
                exc_info=True
            )
            
            # Пытаемся уведомить админов
            bot = data.get('bot')
            if bot:
                notification_manager = ErrorNotificationManager(bot)
                try:
                    await notification_manager.send_error_notification(
                        error_type="critical_error",
                        error_message=f"Critical unhandled error: {str(error)}",
                        functionality="middleware_chain",
                        traceback_text=str(error),
                        additional_info={"event_type": type(event).__name__}
                    )
                except Exception:
                    pass  # Если и это не удалось - ничего не можем сделать
            
            # Не пробрасываем исключение - бот должен продолжать работать
            return None


__all__ = ['ErrorHandlingMiddleware', 'CriticalErrorMiddleware']
