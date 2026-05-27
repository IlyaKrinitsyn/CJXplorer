"""
Навигационный агент.

Анализирует текущее состояние экрана (скриншот + дерево нод)
и решает, какое действие выполнить следующим.
Использует multimodal LLM-вызов (скриншот + JSON нод).
"""

import json
import logging

from openai import AsyncOpenAI

from .config import LLM_API_KEY, LLM_BASE_URL
from .nav_prompts import NAV_SYSTEM_PROMPT, NAV_USER_TEMPLATE

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

VALID_ACTIONS = {"click", "scroll", "type", "input_needed", "back", "done"}
MAX_NODE_DEPTH = 6
MAX_RETRY = 1


def _filter_nodes(nodes: list[dict], depth: int = 0) -> list[dict]:
    """
    Убирает пустые/невидимые ноды и ограничивает глубину дерева
    для экономии токенов в LLM-контексте.
    """
    if depth >= MAX_NODE_DEPTH:
        return []

    result = []
    for node in nodes:
        has_text = bool(node.get("text") or node.get("content_description"))
        has_id = bool(node.get("id"))
        is_interactive = node.get("clickable") or node.get("scrollable")
        children = _filter_nodes(node.get("children", []), depth + 1)

        if has_text or has_id or is_interactive or children:
            filtered = {
                "id": node.get("id", ""),
                "class_name": node.get("class_name", ""),
            }
            if node.get("text"):
                filtered["text"] = node["text"]
            if node.get("content_description"):
                filtered["content_description"] = node["content_description"]
            if node.get("clickable"):
                filtered["clickable"] = True
            if node.get("scrollable"):
                filtered["scrollable"] = True

            bounds = node.get("bounds")
            if bounds:
                filtered["bounds"] = bounds

            if children:
                filtered["children"] = children

            result.append(filtered)

    return result


def _format_action_history(action_history: list[dict]) -> str:
    """Форматирует историю действий в читаемый текст для промпта."""
    if not action_history:
        return "Нет предыдущих действий (первый шаг)."

    lines = []
    for i, entry in enumerate(action_history[-10:], 1):
        action = entry.get("action", "?")
        reason = entry.get("reason", "")
        details = ""
        if action == "click":
            details = f" node_id={entry.get('node_id', '?')}"
        elif action == "scroll":
            details = f" direction={entry.get('direction', '?')}"
        elif action == "type":
            details = f" node_id={entry.get('node_id', '?')}"
        elif action == "input_needed":
            details = f" prompt={entry.get('prompt', '?')}"
        lines.append(f"  {i}. {action}{details}" + (f" — {reason}" if reason else ""))

    return "\n".join(lines)


def _parse_llm_response(text: str) -> dict | None:
    """Извлекает JSON из ответа LLM, даже если он обёрнут в markdown."""
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        inside = False
        for line in lines:
            if line.strip().startswith("```") and not inside:
                inside = True
                continue
            if line.strip() == "```" and inside:
                break
            if inside:
                json_lines.append(line)
        text = "\n".join(json_lines).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("action") in VALID_ACTIONS:
            return parsed
    except json.JSONDecodeError:
        pass

    return None


async def decide_next_action(
    screenshot_b64: str,
    nodes: list[dict],
    task_description: str,
    step: int,
    model: str,
    action_history: list[dict] | None = None,
) -> dict:
    """
    Определяет следующее действие на основе состояния экрана.

    Args:
        screenshot_b64: Скриншот экрана в base64.
        nodes: Дерево нод AccessibilityService.
        task_description: Описание задачи (приложение + CJ).
        step: Текущий номер шага.
        model: Идентификатор LLM-модели.
        action_history: История предыдущих действий (последние N шагов).

    Returns:
        Словарь с действием, например:
        {"action": "click", "node_id": "..."}
        {"action": "scroll", "direction": "down"}
        {"action": "type", "node_id": "...", "text": "..."}
        {"action": "back"}
        {"action": "input_needed", "node_id": "...", "prompt": "Введите логин"}
        {"action": "done"}
    """
    filtered_nodes = _filter_nodes(nodes)
    nodes_json = json.dumps(filtered_nodes, ensure_ascii=False, indent=1)

    history_text = _format_action_history(action_history or [])

    user_text = NAV_USER_TEMPLATE.format(
        task_description=task_description,
        step=step,
        action_history=history_text,
        nodes_json=nodes_json,
    )

    user_content: list[dict] = [
        {"type": "text", "text": user_text},
    ]

    if screenshot_b64:
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{screenshot_b64}",
                "detail": "high",
            },
        })
    else:
        logger.warning(f"Step {step}: no screenshot, text-only LLM call")

    for attempt in range(MAX_RETRY + 1):
        try:
            response = await _client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": NAV_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=512,
            )

            raw = response.choices[0].message.content
            logger.info(f"Step {step}: LLM raw response: {raw[:200]}")

            parsed = _parse_llm_response(raw)
            if parsed:
                logger.info(f"Step {step}: action={parsed.get('action')}")
                return parsed

            if attempt < MAX_RETRY:
                logger.warning(f"Step {step}: invalid JSON, retry {attempt + 1}")
                continue

            logger.error(f"Step {step}: failed to parse after {MAX_RETRY + 1} attempts")
            return {"action": "done", "reason": "Не удалось разобрать ответ LLM"}

        except Exception as e:
            logger.error(f"Step {step}: LLM call failed: {e}")
            if attempt < MAX_RETRY:
                continue
            return {"action": "done", "reason": f"Ошибка LLM: {e}"}
