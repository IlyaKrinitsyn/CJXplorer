"""
Конфигурация бэкенда.

Загружает переменные окружения из .env файла.
Содержит настройки LLM-провайдера, список моделей и параметры навигации.
"""

import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.environ["LLM_API_KEY"]
"""API-ключ для LLM-провайдера (OpenRouter, OpenAI и т.д.)."""

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
"""Базовый URL API. По умолчанию — OpenRouter."""

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o")
"""Модель по умолчанию."""

NAV_MAX_STEPS = int(os.getenv("NAV_MAX_STEPS", "50"))
"""Максимальное количество шагов навигации (защита от зацикливания)."""

AVAILABLE_MODELS = {
    "openai/gpt-4o": "GPT-4o",
    "openai/gpt-4o-mini": "GPT-4o mini",
    "openai/gpt-4.1": "GPT-4.1",
    "anthropic/claude-sonnet-4": "Claude Sonnet 4",
    "google/gemini-2.5-flash": "Gemini 2.5 Flash",
    "google/gemini-2.5-pro": "Gemini 2.5 Pro",
}
"""Словарь доступных моделей: ключ — ID для API, значение — название для UI."""
