"""
Конфигурация Telegram-бота.

Бот больше не вызывает LLM напрямую — обращается к бэкенду по HTTP.
"""

import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
"""Токен Telegram-бота, полученный от @BotFather."""

BACKEND_URL = os.getenv("BACKEND_URL", "http://cjxplorer-core:8000")
"""URL бэкенда CJXplorer."""
