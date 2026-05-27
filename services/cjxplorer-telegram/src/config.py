"""
Конфигурация Telegram-бота.

Бот больше не вызывает LLM напрямую — обращается к бэкенду по HTTP.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

VERSION = (Path(__file__).parent.parent / "VERSION").read_text().strip()
"""Версия сервиса cjxplorer-telegram, читается из файла VERSION."""

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
"""Токен Telegram-бота, полученный от @BotFather."""

BACKEND_URL = os.getenv("BACKEND_URL", "http://cjxplorer-core:8000")
"""URL бэкенда CJXplorer."""
