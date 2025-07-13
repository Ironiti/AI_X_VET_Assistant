import os
from dotenv import load_dotenv
import requests

load_dotenv()

api_key = os.getenv('OPENROUTER_API_KEY')
print(f"API Key: {api_key[:15]}...")

response = requests.get(
    'https://openrouter.ai/api/v1/auth/key',
    headers={'Authorization': f'Bearer {api_key}'}
)
print("Status:", response.status_code)
print("Response:", response.json())