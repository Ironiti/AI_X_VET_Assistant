"""
Пример интеграции системы оценки ответов в обработчик вопросов.
Этот файл показывает, как правильно подключить BotFeedbackSystem к вашему боту.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
import logging

from bot.handlers.bot_feedback_system import BotFeedbackSystem

logger = logging.getLogger(__name__)

# Создаем роутер
feedback_router = Router(name="feedback")


def setup_feedback_handlers(db):
    """
    Настройка обработчиков для системы обратной связи.
    
    Args:
        db: Экземпляр класса Database
        
    Returns:
        Router: Настроенный роутер с обработчиками
    """
    
    # Инициализируем систему обратной связи
    feedback_system = BotFeedbackSystem(db)
    
    @feedback_router.callback_query(F.data.startswith("feedback:"))
    async def handle_feedback_callback(callback: CallbackQuery, state: FSMContext):
        """
        Обработчик нажатий на кнопки оценки.
        
        Обрабатывает три типа действий:
        - feedback:positive:message_id - положительная оценка
        - feedback:negative:message_id - отрицательная оценка
        - feedback:disable:message_id - отключение запросов оценки
        """
        try:
            success = await feedback_system.handle_feedback_callback(
                callback=callback,
                state=state
            )
            
            if success:
                logger.info(
                    f"[FEEDBACK] Successfully processed feedback from "
                    f"user {callback.from_user.id}"
                )
            else:
                logger.warning(
                    f"[FEEDBACK] Failed to process feedback from "
                    f"user {callback.from_user.id}"
                )
                
        except Exception as e:
            logger.error(f"[FEEDBACK] Error in callback handler: {e}")
            import traceback
            traceback.print_exc()
            
            # Уведомляем пользователя об ошибке
            try:
                await callback.answer(
                    "Произошла ошибка. Попробуйте позже.",
                    show_alert=True
                )
            except:
                pass
    
    return feedback_system, feedback_router


# =============================================================================
# ПРИМЕР ИСПОЛЬЗОВАНИЯ В ОБРАБОТЧИКЕ ВОПРОСОВ
# =============================================================================

def create_questions_handler_with_feedback(db, feedback_system):
    """
    Пример создания обработчика вопросов с интегрированной системой оценки.
    
    Args:
        db: Экземпляр Database
        feedback_system: Экземпляр BotFeedbackSystem
        
    Returns:
        Router: Роутер с обработчиками вопросов
    """
    
    questions_router = Router(name="questions_with_feedback")
    
    @questions_router.message(F.text)
    async def handle_question_with_feedback(message: Message, state: FSMContext):
        """
        Обработчик вопросов с автоматическим запросом оценки.
        """
        user_id = message.from_user.id
        question_text = message.text
        
        try:
            # 1. Обрабатываем вопрос (ваша логика)
            # Например, получаем ответ от AI или базы знаний
            # answer_text = await get_answer_from_ai(question_text)
            answer_text = "Это пример ответа на ваш вопрос."
            
            # 2. Отправляем ответ пользователю
            bot_response = await message.answer(answer_text)
            
            # 3. Сохраняем данные в state для последующего использования
            await state.update_data(
                last_question=question_text,
                last_bot_response=answer_text,
                last_bot_response_message_id=bot_response.message_id
            )
            
            # 4. ВАЖНО: Запрашиваем оценку ответа
            feedback_message = await feedback_system.send_feedback_request(
                message=message,
                bot_response_message_id=bot_response.message_id,
                state=state
            )
            
            if feedback_message:
                logger.info(
                    f"[FEEDBACK] Sent feedback request to user {user_id} "
                    f"for message {bot_response.message_id}"
                )
            else:
                logger.debug(
                    f"[FEEDBACK] Skipped feedback request for user {user_id} "
                    "(cooldown or disabled)"
                )
                
        except Exception as e:
            logger.error(f"[QUESTIONS] Error handling question: {e}")
            await message.answer(
                "Произошла ошибка при обработке вопроса. "
                "Пожалуйста, попробуйте еще раз."
            )
    
    return questions_router


# =============================================================================
# ИНТЕГРАЦИЯ В MAIN.PY
# =============================================================================

"""
В вашем main.py добавьте следующий код:

```python
from aiogram import Bot, Dispatcher
from bot.handlers.feedback_integration_example import (
    setup_feedback_handlers,
    create_questions_handler_with_feedback
)
from src.database.models import Database

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database(DB_PATH)

# Настройка системы обратной связи
feedback_system, feedback_router = setup_feedback_handlers(db)

# Создание обработчика вопросов с feedback
questions_router = create_questions_handler_with_feedback(db, feedback_system)

# Регистрация роутеров (ВАЖНО: feedback_router должен быть первым!)
dp.include_router(feedback_router)
dp.include_router(questions_router)

# Запуск бота
await dp.start_polling(bot)
```
"""


# =============================================================================
# ДОПОЛНИТЕЛЬНЫЕ УТИЛИТЫ
# =============================================================================

async def send_feedback_stats_to_admin(bot, admin_id: int, db, days: int = 7):
    """
    Отправляет статистику оценок администратору.
    Можно использовать в ежедневных/еженедельных отчетах.
    
    Args:
        bot: Экземпляр Bot
        admin_id: Telegram ID администратора
        db: Экземпляр Database
        days: Период для анализа
    """
    try:
        stats = await db.get_bot_rating_stats(days)
        
        if not stats or not stats.get('overall'):
            await bot.send_message(
                admin_id,
                "📊 Нет данных об оценках за указанный период."
            )
            return
        
        overall = stats['overall']
        
        # Формируем красивое сообщение
        message = f"""
📊 <b>СТАТИСТИКА ОЦЕНОК ОТВЕТОВ</b>
<i>За последние {days} дней</i>

📈 <b>Общие показатели:</b>
━━━━━━━━━━━━━━━━━━
Всего оценок: {overall['total_ratings']}
Уникальных пользователей: {overall['unique_users']}

👍 Положительные: {overall['positive_count']} ({overall['positive_percentage']:.1f}%)
👎 Отрицательные: {overall['negative_count']} ({overall['negative_percentage']:.1f}%)
🔕 Отклонено: {overall['declined_count']} ({overall['declined_percentage']:.1f}%)

<b>Уровень удовлетворенности:</b> {overall['positive_percentage']:.1f}%
"""
        
        # Добавляем информацию об отключениях
        if stats.get('disabled_users_count', 0) > 0:
            message += f"\n⚠️ Отключили оценки: {stats['disabled_users_count']} пользователей"
        
        # Оценка качества
        satisfaction = overall['positive_percentage']
        if satisfaction >= 80:
            quality_emoji = "✅"
            quality_text = "Отлично"
        elif satisfaction >= 60:
            quality_emoji = "👍"
            quality_text = "Хорошо"
        elif satisfaction >= 40:
            quality_emoji = "⚠️"
            quality_text = "Средне"
        else:
            quality_emoji = "❌"
            quality_text = "Требует внимания"
        
        message += f"\n\n{quality_emoji} <b>Оценка:</b> {quality_text}"
        
        await bot.send_message(
            admin_id,
            message,
            parse_mode="HTML"
        )
        
        logger.info(f"[FEEDBACK] Stats sent to admin {admin_id}")
        
    except Exception as e:
        logger.error(f"[FEEDBACK] Error sending stats to admin: {e}")


async def analyze_negative_feedback(db, days: int = 7, limit: int = 10):
    """
    Анализ отрицательных оценок для выявления проблем.
    
    Args:
        db: Экземпляр Database
        days: Период анализа
        limit: Количество примеров
        
    Returns:
        list: Список отрицательных оценок с деталями
    """
    try:
        from datetime import datetime, timedelta
        
        start_date = datetime.now() - timedelta(days=days)
        
        async with db.db_path as conn:
            import aiosqlite
            async with aiosqlite.connect(db.db_path) as db_conn:
                db_conn.row_factory = aiosqlite.Row
                
                cursor = await db_conn.execute('''
                    SELECT
                        brr.id,
                        brr.user_id,
                        u.name as user_name,
                        brr.question,
                        brr.bot_response,
                        brr.timestamp
                    FROM bot_response_ratings brr
                    JOIN users u ON brr.user_id = u.telegram_id
                    WHERE brr.rating_type = 'negative'
                      AND brr.timestamp >= ?
                    ORDER BY brr.timestamp DESC
                    LIMIT ?
                ''', (start_date, limit))
                
                results = [dict(row) for row in await cursor.fetchall()]
                
                logger.info(
                    f"[FEEDBACK] Found {len(results)} negative ratings "
                    f"in last {days} days"
                )
                
                return results
                
    except Exception as e:
        logger.error(f"[FEEDBACK] Error analyzing negative feedback: {e}")
        return []


# =============================================================================
# КОМАНДЫ ДЛЯ АДМИНИСТРАТОРА
# =============================================================================

def setup_admin_feedback_commands(db):
    """
    Настройка команд для администратора для управления системой оценок.
    """
    
    admin_router = Router(name="admin_feedback")
    
    @admin_router.message(F.text == "📊 Статистика оценок")
    async def show_feedback_stats(message: Message):
        """Показать статистику оценок"""
        
        # Проверка что пользователь - админ
        user = await db.get_user(message.from_user.id)
        if not user or user.get('role') != 'admin':
            return
        
        try:
            stats = await db.get_bot_rating_stats(days=30)
            
            if not stats or not stats.get('overall'):
                await message.answer("📊 Нет данных об оценках.")
                return
            
            overall = stats['overall']
            
            text = f"""
📊 <b>СТАТИСТИКА ОЦЕНОК (30 ДНЕЙ)</b>

Всего оценок: {overall['total_ratings']}
👍 Положительные: {overall['positive_count']} ({overall['positive_percentage']:.1f}%)
👎 Отрицательные: {overall['negative_count']} ({overall['negative_percentage']:.1f}%)
🔕 Отклонено: {overall['declined_count']} ({overall['declined_percentage']:.1f}%)

Уникальных пользователей: {overall['unique_users']}
Отключили оценки: {stats.get('disabled_users_count', 0)}

<b>Уровень удовлетворенности:</b> {overall['positive_percentage']:.1f}%
"""
            
            await message.answer(text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"[ADMIN] Error showing feedback stats: {e}")
            await message.answer("Ошибка при получении статистики.")
    
    return admin_router


# =============================================================================
# ЭКСПОРТ
# =============================================================================

__all__ = [
    'setup_feedback_handlers',
    'create_questions_handler_with_feedback',
    'send_feedback_stats_to_admin',
    'analyze_negative_feedback',
    'setup_admin_feedback_commands'
]
