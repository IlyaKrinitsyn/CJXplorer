import base64
from openai import AsyncOpenAI

from .config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from .prompts import SYSTEM_PROMPT

client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


async def evaluate_screenshots(screenshots: list[bytes]) -> str:
    """
    Evaluates a complete customer journey from a sequence of screenshots.
    Screenshots should be in order of the CJ steps.
    Returns the evaluation text.
    """
    user_content = [
        {
            "type": "text",
            "text": (
                f"Вот {len(screenshots)} скриншотов клиентского пути, "
                "пронумерованных в порядке следования шагов. "
                "Оцени весь путь целиком по критериальной модели."
            ),
        }
    ]

    for i, screenshot in enumerate(screenshots, 1):
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
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=4096,
    )

    return response.choices[0].message.content
