"""
Scheduler для автоматической отправки метрик в последний день месяца
"""
import asyncio
import logging
from datetime import datetime, timedelta
from calendar import monthrange
import os

from utils.metrics_exporter import MetricsExporter
from utils.email_sender import send_monthly_metrics_email
from utils.monthly_metrics_config import merge_monthly_metrics_recipients
from src.database.db_init import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}
DEFAULT_METRICS_SOURCE_NAME = "Telegram"


class MonthlyMetricsScheduler:
    """
    Планировщик для автоматической отправки метрик в последний день месяца
    """
    
    def __init__(self):
        self.is_running = False
        self.task = None
        self.metrics_email = merge_monthly_metrics_recipients(
            os.getenv('METRICS_EMAIL') or os.getenv('EMAIL_TO')
        )
        self.metrics_source_name = os.getenv(
            'METRICS_SOURCE_NAME', DEFAULT_METRICS_SOURCE_NAME
        )
        
    async def check_and_send_metrics(self):
        """
        Проверяет, является ли сегодня последним днем месяца,
        и если да - отправляет метрики на email и очищает данные
        """
        try:
            now = datetime.now()
            current_day = now.day
            current_month = now.month
            current_year = now.year

            # Отчет отправляется в 23:55 последнего дня месяца.
            last_day_of_month = monthrange(current_year, current_month)[1]
            if current_day == last_day_of_month:
                logger.info(
                    "[MONTHLY METRICS] Today is the last day of month: "
                    f"{current_day}/{current_month}/{current_year}"
                )
                
                # Вычисляем количество дней для отчета (весь месяц)
                days_in_month = last_day_of_month
                
                # Формируем название месяца для отчета
                month_name = f"{MONTH_NAMES_RU[current_month]} {current_year}"
                
                logger.info(f"[MONTHLY METRICS] Generating metrics report for {days_in_month} days ({month_name})...")
                
                # Экспортируем метрики в Excel
                exporter = MetricsExporter(db)
                excel_data = await exporter.export_comprehensive_metrics(days=days_in_month)
                
                if not excel_data:
                    logger.error("[MONTHLY METRICS] Failed to generate Excel report")
                    return False
                
                logger.info(f"[MONTHLY METRICS] Excel report generated successfully ({len(excel_data)} bytes)")
                
                # Отправляем на email
                logger.info(f"[MONTHLY METRICS] Sending report to {self.metrics_email}...")
                email_sent = await send_monthly_metrics_email(
                    excel_data=excel_data,
                    month_name=f"{month_name} [{self.metrics_source_name}]",
                    metrics_recipient=self.metrics_email,
                )
                
                if not email_sent:
                    logger.error("[MONTHLY METRICS] Failed to send email report")
                    return False
                
                logger.info("[MONTHLY METRICS] Email report sent successfully")
                logger.info(f"[MONTHLY METRICS] Monthly cycle complete. Data preserved for annual metrics.")
                return True
            else:
                days_until_end = last_day_of_month - current_day
                logger.debug(
                    f"[MONTHLY METRICS] Not the last day yet. "
                    f"{days_until_end} days until month end"
                )
                return False
                
        except Exception as e:
            logger.error(f"[MONTHLY METRICS] Error in check_and_send_metrics: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def run_daily_check(self):
        """
        Запускает ежедневную проверку в 23:55.
        """
        logger.info("[MONTHLY METRICS SCHEDULER] Starting daily check loop...")
        
        while self.is_running:
            try:
                now = datetime.now()
                
                # Следующая проверка — в 23:55 по локальному времени сервера.
                next_check_time = now.replace(hour=23, minute=55, second=0, microsecond=0)
                
                if now >= next_check_time:
                    # Если 23:55 уже прошло, планируем на завтра.
                    next_check_time += timedelta(days=1)
                
                # Вычисляем время ожидания до следующей проверки
                wait_seconds = (next_check_time - now).total_seconds()
                
                logger.info(f"[MONTHLY METRICS SCHEDULER] Next check at: {next_check_time.strftime('%d.%m.%Y %H:%M')}")
                logger.info(f"[MONTHLY METRICS SCHEDULER] Waiting {wait_seconds / 3600:.1f} hours...")
                
                # Ждем до следующей проверки
                await asyncio.sleep(wait_seconds)
                
                # Выполняем проверку
                if self.is_running:  # Проверяем, что не было остановки во время ожидания
                    logger.info("[MONTHLY METRICS SCHEDULER] Running scheduled check...")
                    await self.check_and_send_metrics()
                    
            except asyncio.CancelledError:
                logger.info("[MONTHLY METRICS SCHEDULER] Task cancelled, stopping...")
                break
            except Exception as e:
                logger.error(f"[MONTHLY METRICS SCHEDULER] Error in run_daily_check: {e}")
                import traceback
                traceback.print_exc()
                # Ждем час перед повторной попыткой в случае ошибки
                await asyncio.sleep(3600)
    
    async def start(self):
        """Запускает scheduler"""
        if self.is_running:
            logger.warning("[MONTHLY METRICS SCHEDULER] Already running")
            return
        
        if not self.metrics_email:
            logger.error("[MONTHLY METRICS SCHEDULER] METRICS_EMAIL not configured in .env")
            return
        
        logger.info(f"[MONTHLY METRICS SCHEDULER] Starting scheduler (email: {self.metrics_email})")
        self.is_running = True
        self.task = asyncio.create_task(self.run_daily_check())
        logger.info("[MONTHLY METRICS SCHEDULER] Scheduler started successfully")
    
    async def stop(self):
        """Останавливает scheduler"""
        if not self.is_running:
            return
        
        logger.info("[MONTHLY METRICS SCHEDULER] Stopping scheduler...")
        self.is_running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("[MONTHLY METRICS SCHEDULER] Scheduler stopped")
    
    async def force_send_now(self):
        """
        Принудительная отправка метрик прямо сейчас (для тестирования)
        Отправляет метрики за текущий месяц БЕЗ очистки данных
        """
        try:
            now = datetime.now()
            current_month = now.month
            current_year = now.year
            current_day = now.day
            
            month_name = f"{MONTH_NAMES_RU[current_month]} {current_year} (тестовая отправка)"
            
            logger.info(f"[MONTHLY METRICS] FORCE SEND: Generating report for current period ({current_day} days)...")
            
            # Генерируем отчет за текущее количество дней месяца
            exporter = MetricsExporter(db)
            excel_data = await exporter.export_comprehensive_metrics(days=current_day)
            
            if not excel_data:
                logger.error("[MONTHLY METRICS] Failed to generate Excel report")
                return False
            
            logger.info(f"[MONTHLY METRICS] Excel report generated ({len(excel_data)} bytes)")
            
            # Отправляем на email
            email_sent = await send_monthly_metrics_email(
                excel_data=excel_data,
                month_name=f"{month_name} [{self.metrics_source_name}]",
                metrics_recipient=self.metrics_email,
            )
            
            if email_sent:
                logger.info("[MONTHLY METRICS] FORCE SEND: Email sent successfully (data NOT cleared)")
                return True
            else:
                logger.error("[MONTHLY METRICS] FORCE SEND: Failed to send email")
                return False
                
        except Exception as e:
            logger.error(f"[MONTHLY METRICS] Error in force_send_now: {e}")
            import traceback
            traceback.print_exc()
            return False


# Глобальный экземпляр scheduler
monthly_scheduler = MonthlyMetricsScheduler()
