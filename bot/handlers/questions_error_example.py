"""
Пример интеграции системы обработки ошибок в существующий код

Этот файл показывает, как обновить существующие обработчики
для использования новой системы обработки ошибок.

Основные изменения:
1. Заменить общие try-except блоки на специфичные обработчики
2. Использовать декоратор @with_error_handling для автоматической обработки
3. Заменить стандартные сообщения об ошибках на информативные
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from bot.handlers.error_handler import (
    with_error_handling,
    get_user_friendly_error_message,
    ErrorType,
    handle_error_gracefully
)
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# ВАРИАНТ 1: Использование декоратора (рекомендуется для простых случаев)
# ============================================================================

@with_error_handling("code_search")
async def handle_code_search_decorated(message: Message, state: FSMContext):
    """
    Пример использования декоратора для автоматической обработки ошибок
    
    Декоратор автоматически:
    - Перехватывает все исключения
    - Отправляет уведомление администратору
    - Показывает пользователю информативное сообщение
    - Логирует инцидент
    """
    # Ваш код здесь - любые ошибки будут обработаны автоматически
    processor = DataProcessor()
    processor.load_vector_store()
    
    results = processor.search_test(filter_dict={"test_code": "AN116"})
    # ...


# ============================================================================
# ВАРИАНТ 2: Явная обработка с контролем (для сложных случаев)
# ============================================================================

async def handle_code_search_manual(message: Message, state: FSMContext):
    """
    Пример явной обработки ошибок с дополнительным контролем
    
    Используйте этот подход когда нужно:
    - Специфичная обработка разных типов ошибок
    - Дополнительная логика перед отправкой уведомления
    - Частичная обработка (graceful degradation)
    """
    user_id = message.from_user.id
    bot = message.bot
    
    try:
        # Пытаемся выполнить операцию
        processor = DataProcessor()
        processor.load_vector_store()
        
        results = processor.search_test(filter_dict={"test_code": "AN116"})
        
        if not results:
            # Результатов нет - это не ошибка, но нужно сообщить пользователю
            await message.answer(
                "❌ Тест не найден в базе данных.\n\n"
                "💡 Попробуйте:\n"
                "• Проверить правильность кода\n"
                "• Использовать поиск по названию\n"
                "• Связаться со специалистом",
                reply_markup=get_user_friendly_error_message(ErrorType.VECTOR_DB_ERROR)[1]
            )
            return
        
        # Обработка результатов...
        
    except asyncio.TimeoutError as e:
        # Специфичная обработка таймаута
        logger.warning(f"[CODE_SEARCH] Timeout for user {user_id}")
        
        message_text, keyboard = get_user_friendly_error_message(
            error_type=ErrorType.TIMEOUT,
            with_retry=True,
            with_contact_support=True
        )
        
        await message.answer(message_text, parse_mode="HTML", reply_markup=keyboard)
        
        # Отправляем уведомление админу
        await handle_error_gracefully(
            error=e,
            bot=bot,
            user_id=user_id,
            chat_id=message.chat.id,
            functionality="code_search",
            additional_info={"query": message.text}
        )
        
    except Exception as e:
        # Общая обработка всех остальных ошибок
        logger.error(f"[CODE_SEARCH] Unexpected error for user {user_id}: {e}")
        
        # Обрабатываем gracefully
        await handle_error_gracefully(
            error=e,
            bot=bot,
            user_id=user_id,
            chat_id=message.chat.id,
            functionality="code_search",
            additional_info={"query": message.text}
        )


# ============================================================================
# ВАРИАНТ 3: Graceful degradation (постепенная деградация)
# ============================================================================

async def handle_general_question_with_fallback(
    message: Message,
    state: FSMContext,
    question_text: str
):
    """
    Пример graceful degradation - бот остается отзывчивым при частичных сбоях
    
    Стратегия:
    1. Пытается использовать LLM
    2. Если LLM недоступен - пытается поиск по базе
    3. Если и это не работает - предлагает связаться со специалистом
    """
    user_id = message.from_user.id
    bot = message.bot
    
    # Уровень 1: Пытаемся использовать LLM
    try:
        logger.info(f"[GENERAL_Q] Trying LLM for user {user_id}")
        
        response = await llm.agenerate([
            [
                SystemMessage(content="You are a helpful assistant"),
                HumanMessage(content=question_text),
            ]
        ])
        
        answer = response.generations[0][0].text.strip()
        await message.answer(answer, parse_mode="HTML")
        return
        
    except asyncio.TimeoutError:
        logger.warning(f"[GENERAL_Q] LLM timeout for user {user_id}, falling back to search")
        
        # Уровень 2: Если LLM таймаутит - пытаемся поиск
        try:
            processor = DataProcessor()
            processor.load_vector_store()
            
            results = processor.search_test(query=question_text, top_k=5)
            
            if results:
                # Формируем ответ из результатов поиска
                response = "🔍 <b>Найденные тесты по вашему запросу:</b>\n\n"
                for doc, score in results[:3]:
                    test_code = doc.metadata.get('test_code')
                    test_name = doc.metadata.get('test_name')
                    response += f"• {test_code} - {test_name}\n"
                
                response += "\n💡 <i>Нажмите на код для подробной информации</i>"
                
                await message.answer(
                    response,
                    parse_mode="HTML"
                )
                
                # Уведомляем админа о деградации
                await handle_error_gracefully(
                    error=asyncio.TimeoutError("LLM timeout - used fallback search"),
                    bot=bot,
                    user_id=user_id,
                    chat_id=message.chat.id,
                    functionality="general_question_llm",
                    additional_info={
                        "fallback": "search",
                        "query": question_text
                    }
                )
                return
            
            else:
                # Нет результатов поиска
                raise ValueError("No search results")
                
        except Exception as search_error:
            logger.error(f"[GENERAL_Q] Search fallback failed: {search_error}")
    
    except Exception as llm_error:
        logger.error(f"[GENERAL_Q] LLM error: {llm_error}")
    
    # Уровень 3: Если все методы не сработали - предлагаем связаться
    message_text, keyboard = get_user_friendly_error_message(
        error_type=ErrorType.LLM_ERROR,
        with_retry=True,
        with_contact_support=True,
        custom_message=(
            "🤖 <b>Проблема с обработкой запроса</b>\n\n"
            "К сожалению, сейчас не могу обработать ваш вопрос из-за технических проблем.\n\n"
            "💡 <b>Вы можете:</b>\n"
            "• Попробовать найти тест по коду\n"
            "• Связаться со специалистом напрямую\n"
            "• Повторить попытку через несколько минут"
        )
    )
    
    await message.answer(message_text, parse_mode="HTML", reply_markup=keyboard)
    
    # Уведомляем админа о полном сбое
    await handle_error_gracefully(
        error=Exception("Complete failure in general_question - all fallbacks failed"),
        bot=bot,
        user_id=user_id,
        chat_id=message.chat.id,
        functionality="general_question_complete",
        additional_info={"query": question_text}
    )


# ============================================================================
# ВАРИАНТ 4: Замена существующих обработок ошибок
# ============================================================================

# БЫЛО (старый код):
async def old_handle_code_search(message: Message, state: FSMContext):
    try:
        processor = DataProcessor()
        processor.load_vector_store()
        results = processor.search_test(filter_dict={"test_code": "AN116"})
        
        if not results:
            await message.answer("⚠️ Ошибка поиска. Попробуйте позже.")  # ❌ Плохо
            return
        
        # ...
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer("⚠️ Ошибка при поиске. Попробуйте позже")  # ❌ Плохо


# СТАЛО (новый код):
async def new_handle_code_search(message: Message, state: FSMContext):
    try:
        processor = DataProcessor()
        processor.load_vector_store()
        results = processor.search_test(filter_dict={"test_code": "AN116"})
        
        if not results:
            # ✅ Информативное сообщение с кнопками
            message_text, keyboard = get_user_friendly_error_message(
                error_type=ErrorType.VECTOR_DB_ERROR,
                with_retry=True,
                with_contact_support=True
            )
            await message.answer(message_text, parse_mode="HTML", reply_markup=keyboard)
            return
        
        # ...
        
    except Exception as e:
        # ✅ Полноценная обработка с уведомлением админа
        await handle_error_gracefully(
            error=e,
            bot=message.bot,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            functionality="code_search",
            additional_info={"test_code": "AN116"}
        )


# ============================================================================
# ИНСТРУКЦИИ ПО ОБНОВЛЕНИЮ СУЩЕСТВУЮЩЕГО КОДА
# ============================================================================

"""
ШАГ 1: Найти все места со старыми сообщениями об ошибках
-------
Ищите паттерны вроде:
- "⚠️ Ошибка поиска"  
- "⚠️ Ошибка при загрузке"
- "Попробуйте позже"

ШАГ 2: Определить тип ошибки
-------
- Таймауты -> ErrorType.TIMEOUT
- API ошибки -> ErrorType.API_ERROR
- Ошибки БД -> ErrorType.DATABASE_ERROR
- Векторная БД -> ErrorType.VECTOR_DB_ERROR
- LLM -> ErrorType.LLM_ERROR

ШАГ 3: Заменить обработку
-------
Вместо:
    await message.answer("⚠️ Ошибка поиска. Попробуйте позже.")

Использовать:
    message_text, keyboard = get_user_friendly_error_message(
        error_type=ErrorType.VECTOR_DB_ERROR,
        with_retry=True,
        with_contact_support=True
    )
    await message.answer(message_text, parse_mode="HTML", reply_markup=keyboard)
    
    # И уведомить админа
    await handle_error_gracefully(
        error=e,
        bot=message.bot,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        functionality="название_функции"
    )

ШАГ 4: Добавить middleware (в bot/__init__.py)
-------
from bot.middleware.error_middleware import ErrorHandlingMiddleware

# После других middleware:
dp.message.middleware(ErrorHandlingMiddleware())
dp.callback_query.middleware(ErrorHandlingMiddleware())

ШАГ 5: Добавить переменные окружения (.env)
-------
# ID администраторов для уведомлений (через запятую)
ADMIN_IDS=123456789,987654321

# ID группы для уведомлений (опционально)
ADMIN_GROUP_ID=-1001234567890
"""
