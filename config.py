import os
from dotenv import load_dotenv

load_dotenv()

# API
BOT_API_KEY = os.getenv('BOT_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
DEEPINFRA_API_KEY = os.getenv('DEEPINFRA_API_KEY')

# db
DATABASE_PATH = 'vet_clinic.db'

# Gmail SMTP config
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_LOGIN = os.getenv('EMAIL_LOGIN')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_TO = os.getenv('EMAIL_TO')
