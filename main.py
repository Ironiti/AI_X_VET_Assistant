import asyncio
import logging
from datetime import datetime
from bot.handlers import bot, dp
from src.database.db_init import db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные флаги для управления задачами
running_tasks = []
shutdown_event = asyncio.Event()


async def periodic_session_cleanup():
    """Периодически закрывает неактивные сессии (каждые 60 секунд)"""
    while not shutdown_event.is_set():
        try:
            closed = await db.close_inactive_sessions(inactivity_minutes=3)
            if closed > 0:
                logger.info(f"[SESSIONS] Closed {closed} inactive sessions")
        except Exception as e:
            logger.error(f"[SESSIONS] Cleanup error: {e}")
        
        # Ждем 60 секунд или сигнал остановки
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            continue


async def periodic_metrics_update():
    """Периодически обновляет метрики (каждые 5 минут)"""
    while not shutdown_event.is_set():
        try:
            # Обновляем различные метрики
            await db.update_daily_metrics()
            await db.update_quality_metrics()
            await db.update_system_metrics()
            
            logger.info("[METRICS] Daily metrics updated")
        except Exception as e:
            logger.error(f"[METRICS] Update error: {e}")
        
        # Ждем 5 минут или сигнал остановки
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            continue


async def periodic_cache_cleanup():
    """Периодически очищает кэш (каждые 10 минут)"""
    while not shutdown_event.is_set():
        try:
            # Очищаем кэш пользователей
            if hasattr(db, 'clear_user_cache'):
                db.clear_user_cache()
                logger.info("[CACHE] User cache cleared")
        except Exception as e:
            logger.error(f"[CACHE] Cleanup error: {e}")
        
        # Ждем 10 минут или сигнал остановки
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=600)
        except asyncio.TimeoutError:
            continue


async def startup_tasks():
    """Выполняет задачи при запуске бота"""
    try:
        # Создаем таблицы и индексы
        await db.create_tables()
        logger.info("[STARTUP] Database tables and indexes created")
        
        # Инициализируем векторное хранилище если нужно
        if hasattr(db, 'test_processor'):
            db.test_processor.load_vector_store()
            logger.info("[STARTUP] Vector store loaded")
        
        # Закрываем старые незавершенные сессии
        closed = await db.close_inactive_sessions(inactivity_minutes=180)
        if closed > 0:
            logger.info(f"[STARTUP] Closed {closed} old sessions")
        
        # Обновляем метрики
        await db.update_daily_metrics()
        await db.update_quality_metrics()
        logger.info("[STARTUP] Initial metrics updated")
        
    except Exception as e:
        logger.error(f"[STARTUP] Error during startup: {e}")
        raise


async def shutdown_tasks():
    """Выполняет задачи при остановке бота"""
    try:
        logger.info("[SHUTDOWN] Starting graceful shutdown...")
        
        # Устанавливаем флаг остановки
        shutdown_event.set()
        
        # Ждем завершения всех периодических задач
        if running_tasks:
            await asyncio.gather(*running_tasks, return_exceptions=True)
        
        # Закрываем все активные сессии
        closed = await db.close_inactive_sessions(inactivity_minutes=0)
        logger.info(f"[SHUTDOWN] Closed {closed} active sessions")
        
        # Финальное обновление метрик
        await db.update_daily_metrics()
        logger.info("[SHUTDOWN] Final metrics saved")
        
    except Exception as e:
        logger.error(f"[SHUTDOWN] Error during shutdown: {e}")


async def main():
    try:
        # Выполняем задачи запуска
        await startup_tasks()
        
        # Запускаем периодические задачи
        running_tasks.append(asyncio.create_task(periodic_session_cleanup()))
        running_tasks.append(asyncio.create_task(periodic_metrics_update()))
        running_tasks.append(asyncio.create_task(periodic_cache_cleanup()))
        
        logger.info("[INFO] Starting bot polling...")
        
        # Удаляем вебхук и начинаем polling
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Запускаем бота
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"[MAIN] Critical error: {e}")
        raise
    finally:
        # Выполняем задачи остановки
        await shutdown_tasks()


if __name__ == "__main__":
    try:
        logger.info(f"[START] Bot starting at {datetime.now()}")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[STOP] Bot stopped by user")
    except Exception as e:
        logger.error(f"[FATAL] Bot crashed: {e}")
    finally:
        logger.info("[END] Bot shutdown complete")
