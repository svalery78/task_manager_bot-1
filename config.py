# config.py
import os
from dotenv import load_dotenv

load_dotenv() # Загружаем переменные окружения из .env файла

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
# Выберите модель, например: "openai/gpt-3.5-turbo" или "mistralai/mixtral-8x7b-instruct-v0.1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///tasks.db")