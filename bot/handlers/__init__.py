from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.poll_sender import poll_callback_router
from bot.handlers.registration import registration_router
from bot.handlers.feedback import feedback_router
from bot.handlers.activation import activation_router
from bot.handlers.questions import questions_router
from bot.handlers.admin import admin_router
from bot.handlers.help import help_router
from bot.handlers.content import content_router
from bot.handlers.news import news_router
from bot.handlers.utils import gif_router, file_router
from bot.handlers.faq_handler import faq_router
from bot.handlers.rating_feedback import rating_feedback_router  # Система оценки ответов
from bot.handlers.error_callbacks import error_callbacks_router  # ✅ НОВОЕ: Обработка ошибок - callback'и
from bot.middleware.metrics_middleware import MetricsMiddleware
from bot.middleware.state_recovery_middleware import StateRecoveryMiddleware
from bot.middleware.error_middleware import ErrorHandlingMiddleware  # ✅ НОВОЕ: Обработка ошибок
from bot.middleware.menu_refresh_middleware import MenuRefreshMiddleware
from bot.telegram_proxy import select_telegram_proxy
# from .questions import questions_router, questions_callbacks_router
from config import (
    BOT_API_KEY,
    PROXY_URL,
    TELEGRAM_PROXY_CHECK_TIMEOUT,
    TELEGRAM_PROXY_PREFLIGHT_ENABLED,
    TELEGRAM_RESERVE_PROXY_URL,
)

if not BOT_API_KEY:
    raise RuntimeError('BOT_API_KEY not found.')

selected_proxy = select_telegram_proxy(
    bot_token=BOT_API_KEY,
    primary_proxy_url=PROXY_URL,
    reserve_proxy_url=TELEGRAM_RESERVE_PROXY_URL,
    preflight_enabled=TELEGRAM_PROXY_PREFLIGHT_ENABLED,
    timeout=TELEGRAM_PROXY_CHECK_TIMEOUT,
)
session = AiohttpSession(proxy=selected_proxy) if selected_proxy else AiohttpSession()

bot = Bot(
    token=BOT_API_KEY,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

# Регистрация middleware (порядок важен!)
# 1. ErrorHandlingMiddleware - глобальная обработка ошибок (первым!)
dp.message.middleware(ErrorHandlingMiddleware())
dp.callback_query.middleware(ErrorHandlingMiddleware())

# 2. StateRecoveryMiddleware - восстанавливает состояние после перезагрузки
dp.message.middleware(StateRecoveryMiddleware())
dp.callback_query.middleware(StateRecoveryMiddleware())

# 3. MetricsMiddleware - записывает метрики
dp.message.middleware(MetricsMiddleware())
dp.callback_query.middleware(MetricsMiddleware())

# Refresh an outdated reply keyboard only after a safe user interaction.
dp.message.middleware(MenuRefreshMiddleware())

# Регистрация роутеров (порядок важен!)
# rating_feedback_router должен быть ПЕРВЫМ для обработки callback'ов оценки
dp.include_router(rating_feedback_router)  # ✅ НОВОЕ: Система оценки ответов
dp.include_router(error_callbacks_router)  # ✅ НОВОЕ: Обработка ошибок - callback'и

dp.include_router(registration_router)
# dp.include_router(questions_callbacks_router)
dp.include_router(feedback_router)
dp.include_router(poll_callback_router)
dp.include_router(activation_router)
dp.include_router(content_router)
dp.include_router(news_router)
dp.include_router(questions_router)
dp.include_router(admin_router)
dp.include_router(help_router)
dp.include_router(gif_router)
dp.include_router(faq_router)

# dp.include_router(file_router)
