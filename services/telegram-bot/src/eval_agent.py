"""
Агент оценки клиентских путей.

Отправляет скриншоты CJ в LLM-модель вместе с системным промптом
и возвращает текстовую оценку по критериальной модели.
"""

import base64
from openai import AsyncOpenAI

from .config import LLM_API_KEY, LLM_BASE_URL
from .prompts import SYSTEM_PROMPT

client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def _pluralize(n: int, one: str, few: str, many: str) -> str:
    """Склонение существительного по числительному (русский язык)."""
    if 11 <= n % 100 <= 19:
        return f"{n} {many}"
    mod = n % 10
    if mod == 1:
        return f"{n} {one}"
    if 2 <= mod <= 4:
        return f"{n} {few}"
    return f"{n} {many}"


async def evaluate_screenshots(screenshots: list[bytes], model: str) -> str:
    """
    Оценивает клиентский путь по набору скриншотов.

    Args:
        screenshots: Список скриншотов в байтах, упорядоченных по шагам CJ.
        model: Идентификатор LLM-модели (например, 'openai/gpt-4o').

    Returns:
        Текст оценки в формате HTML для Telegram.
    """
    count = _pluralize(len(screenshots), "скриншот", "скриншота", "скриншотов")
    user_content = [
        {
            "type": "text",
            "text": (
                f"Вот {count} клиентского пути, "
                "пронумерованных в порядке следования шагов. "
                "Оцени весь путь целиком по критериальной модели."
            ),
        }
    ]

    for screenshot in screenshots:
        b64 = base64.b64encode(screenshot).decode("utf-8")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}",
                    "detail": "high",
                },
            }
        )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=4096,
    )

    return response.choices[0].message.content
