"""
Промпты для всех агентов CJXplorer.

Каждый файл содержит промпты для одной фичи:
- eval_prompts: оценка клиентского пути
- improve_prompts: рекомендации по улучшению
- nav_prompts: навигация по приложению
- goal_prompts: декомпозиция задачи на подцели
- tone: общий стиль и тональность
"""

from .eval_prompts import SYSTEM_PROMPT
from .goal_prompts import GOAL_DECOMPOSE_SYSTEM, GOAL_DECOMPOSE_USER
from .improve_prompts import IMPROVE_PROMPT
from .nav_prompts import NAV_SYSTEM_PROMPT, NAV_USER_TEMPLATE
from .tone import TONE

__all__ = [
    "SYSTEM_PROMPT",
    "GOAL_DECOMPOSE_SYSTEM",
    "GOAL_DECOMPOSE_USER",
    "IMPROVE_PROMPT",
    "NAV_SYSTEM_PROMPT",
    "NAV_USER_TEMPLATE",
    "TONE",
]
