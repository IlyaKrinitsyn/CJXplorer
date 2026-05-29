"""
Агент оценки и улучшения клиентских путей.

Отправляет скриншоты CJ в LLM-модель вместе с системным промптом
и возвращает текстовую оценку или рекомендации по улучшению.
"""

import base64
from openai import AsyncOpenAI

from .config import LLM_API_KEY, LLM_BASE_URL
from .prompts.eval_prompts import SYSTEM_PROMPT
from .prompts.improve_prompts import IMPROVE_PROMPT
from .utils import pluralize

client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def _build_screenshots_content(screenshots: list[bytes]) -> list[dict]:
    """Собирает список image_url блоков из скриншотов."""
    content = []
    for screenshot in screenshots:
        b64 = base64.b64encode(screenshot).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64}",
                "detail": "high",
            },
        })
    return content


async def evaluate_screenshots(screenshots: list[bytes], model: str) -> str:
    """
    Оценивает клиентский путь по набору скриншотов.

    Args:
        screenshots: Список скриншотов в байтах, упорядоченных по шагам CJ.
        model: Идентификатор LLM-модели (например, 'openai/gpt-4o').

    Returns:
        Текст оценки в формате HTML для Telegram.
    """
    count = pluralize(len(screenshots), "скриншот", "скриншота", "скриншотов")
    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Вот {count} клиентского пути, "
                "пронумерованных в порядке следования шагов. "
                "Оцени весь путь целиком по критериальной модели."
            ),
        },
        *_build_screenshots_content(screenshots),
    ]

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=4096,
    )

    return response.choices[0].message.content


async def suggest_improvements(
    screenshots: list[bytes], evaluation_result: str, model: str
) -> str:
    """
    Анализирует скриншоты CJ и формирует конкретные рекомендации по улучшению.

    Args:
        screenshots: Те же скриншоты, что использовались для оценки.
        evaluation_result: Текст предыдущей оценки (контекст для агента).
        model: Идентификатор LLM-модели.

    Returns:
        Текст рекомендаций в формате HTML для Telegram.
    """
    count = pluralize(len(screenshots), "скриншот", "скриншота", "скриншотов")
    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"Вот {count} клиентского пути и результат предыдущей оценки.\n\n"
                f"РЕЗУЛЬТАТ ОЦЕНКИ:\n{evaluation_result}\n\n"
                "Проанализируй скриншоты заново и дай конкретные рекомендации "
                "по улучшению клиентского пути по всем 7 направлениям."
            ),
        },
        *_build_screenshots_content(screenshots),
    ]

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": IMPROVE_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=4096,
    )

    return response.choices[0].message.content
