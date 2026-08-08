import os
from dotenv import load_dotenv

load_dotenv(override=True)

# API
BOT_API_KEY = os.getenv('BOT_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
DEEPINFRA_API_KEY = os.getenv('DEEPINFRA_API_KEY')
POLZA_AI_API_KEY = os.getenv('POLZA_AI_API_KEY')

# Telegram-only proxy fallback. Keep X-Lab traffic independent from other bots.
PROXY_URL = os.getenv('PROXY_URL')
TELEGRAM_RESERVE_PROXY_URL = (
    os.getenv('TELEGRAM_RESERVE_PROXY_URL')
    or os.getenv('RESERVE_PROXY_URL')
)
TELEGRAM_PROXY_PREFLIGHT_ENABLED = os.getenv('TELEGRAM_PROXY_PREFLIGHT_ENABLED', '1')
TELEGRAM_PROXY_CHECK_TIMEOUT = float(os.getenv('TELEGRAM_PROXY_CHECK_TIMEOUT', '5'))

# Gmail SMTP config
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_LOGIN = os.getenv('EMAIL_LOGIN')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_TO = os.getenv('EMAIL_TO')

# Increase this value whenever the Telegram reply-menu structure changes.
MENU_VERSION = os.getenv('MENU_VERSION', '2026-08-08.1').strip() or '2026-08-08.1'

