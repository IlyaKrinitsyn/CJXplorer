"""
Навигационный агент.

Анализирует текущее состояние экрана (скриншот + дерево нод)
и решает, какое действие выполнить следующим.

Полная реализация — Шаг 2. Сейчас — заглушка.
"""

import logging

logger = logging.getLogger(__name__)


async def decide_next_action(
    screenshot_b64: str,
    nodes: list[dict],
    task_description: str,
    step: int,
    model: str,
) -> dict:
    """
    Определяет следующее действие на основе состояния экрана.

    Args:
        screenshot_b64: Скриншот экрана в base64.
        nodes: Дерево нод AccessibilityService.
        task_description: Описание задачи (приложение + CJ).
        step: Текущий номер шага.
        model: Идентификатор LLM-модели.

    Returns:
        Словарь с действием, например:
        {"action": "click", "node_id": "..."}
        {"action": "scroll", "direction": "down"}
        {"action": "type", "node_id": "...", "text": "..."}
        {"action": "back"}
        {"action": "input_needed", "node_id": "...", "prompt": "Введите логин"}
        {"action": "done"}
    """
    # Заглушка — будет заменена на LLM-вызов в Шаге 2
    logger.info(f"Step {step}: nav_agent stub called for '{task_description}'")
    return {"action": "done"}
