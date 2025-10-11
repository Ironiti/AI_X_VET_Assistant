"""
Middleware модули для бота
"""
from bot.middleware.metrics_middleware import MetricsMiddleware, daily_updater

__all__ = ['MetricsMiddleware', 'daily_updater']