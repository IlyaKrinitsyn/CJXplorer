"""
Навигационный агент.

Анализирует текущее состояние экрана (скриншот + дерево нод)
и решает, какое действие выполнить следующим.
Использует multimodal LLM-вызов (скриншот + JSON нод).
"""

import json
import logging
import time

from openai import AsyncOpenAI

from .config import LLM_API_KEY, LLM_BASE_URL
from .nav_prompts import NAV_SYSTEM_PROMPT, NAV_USER_TEMPLATE

logger = logging.getLogger(__name__)

logger.info(f"[NAV] LLM client: base_url={LLM_BASE_URL}, api_key={'set' if LLM_API_KEY else 'EMPTY'}")
_client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

VALID_ACTIONS = {"click", "scroll", "type", "input_needed", "back", "done"}
MAX_RETRY = 1
MAX_WALK_DEPTH = 30


def _count_nodes(nodes: list[dict]) -> int:
    """Рекурсивно считает общее количество нод в дереве."""
    total = 0
    for node in nodes:
        total += 1
        total += _count_nodes(node.get("children", []))
    return total


def _flatten_nodes(nodes: list[dict]) -> list[dict]:
    """
    Обходит всё дерево нод без ограничения глубины и собирает
    плоский список элементов, полезных для навигации.

    Включает:
    - интерактивные элементы (clickable / scrollable)
    - элементы с текстом или content_description

    Результат — компактный список без вложенности,
    напрямую пригодный для LLM.
    """
    result = []

    def _walk(node_list: list[dict], depth: int = 0):
        if depth > MAX_WALK_DEPTH:
            return
        for node in node_list:
            has_text = bool(node.get("text") or node.get("content_description"))
            is_interactive = node.get("clickable") or node.get("scrollable")

            if has_text or is_interactive:
                flat: dict = {}
                nid = node.get("id", "")
                if nid:
                    flat["id"] = nid
                if node.get("text"):
                    flat["text"] = node["text"]
                if node.get("content_description"):
                    flat["desc"] = node["content_description"]
                if node.get("clickable"):
                    flat["clickable"] = True
                if node.get("scrollable"):
                    flat["scrollable"] = True
                bounds = node.get("bounds")
                if bounds:
                    flat["bounds"] = bounds
                result.append(flat)

            _walk(node.get("children", []), depth + 1)

    _walk(nodes)
    return result


def _format_elements_for_prompt(elements: list[dict]) -> str:
    """Форматирует плоский список элементов в читаемый текст для промпта."""
    if not elements:
        return "(нет доступных элементов — ориентируйся только по скриншоту)"

    lines = []
    for i, el in enumerate(elements):
        parts = [f"#{i}"]
        if el.get("clickable"):
            parts.append("[clickable]")
        if el.get("scrollable"):
            parts.append("[scrollable]")
        if el.get("id"):
            parts.append(f'id="{el["id"]}"')
        if el.get("text"):
            parts.append(f'text="{el["text"]}"')
        if el.get("desc"):
            parts.append(f'desc="{el["desc"]}"')
        b = el.get("bounds")
        if b:
            parts.append(f'bounds=({b.get("left",0)},{b.get("top",0)},{b.get("right",0)},{b.get("bottom",0)})')
        lines.append(" ".join(parts))

    return "\n".join(lines)


def _get_phase_hint(action_history: list[dict], step: int) -> str:
    """Определяет фазу навигации и возвращает подсказку для промпта."""
    if step <= 1:
        return "ФАЗА: Найди и открой целевое приложение. Если видишь его иконку — КЛИКНИ по ней.\n"

    has_click = any(a.get("action") == "click" for a in action_history)
    only_scrolls = all(
        a.get("action") in ("scroll", "back") for a in action_history
    )

    if only_scrolls:
        scroll_count = sum(1 for a in action_history if a.get("action") == "scroll")
        if scroll_count >= 3:
            return (
                "ФАЗА: Приложение не найдено после нескольких скроллов. "
                "Если не видишь его — ответь done.\n"
            )
        return "ФАЗА: Ищем приложение. Если видишь его иконку — КЛИКНИ, не скролль мимо!\n"

    if has_click:
        return "ФАЗА: Приложение открыто. Выполняй шаги клиентского пути.\n"

    return ""


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
    """
    Извлекает JSON из ответа LLM.
    Поддерживает: чистый JSON, markdown-блок, JSON внутри текста.
    """
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

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict) and parsed.get("action") in VALID_ACTIONS:
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def _find_clickable_container(
    target: dict, elements: list[dict]
) -> dict | None:
    """
    Если target не clickable, ищет ближайший clickable элемент,
    чьи bounds полностью содержат target.
    Выбирает самый маленький (ближайший) контейнер.
    """
    tb = target.get("bounds")
    if not tb:
        return None

    best = None
    best_area = float("inf")
    for el in elements:
        if not el.get("clickable"):
            continue
        eb = el.get("bounds")
        if not eb:
            continue
        if (eb.get("left", 0) <= tb.get("left", 0) and
                eb.get("top", 0) <= tb.get("top", 0) and
                eb.get("right", 0) >= tb.get("right", 0) and
                eb.get("bottom", 0) >= tb.get("bottom", 0)):
            area = ((eb.get("right", 0) - eb.get("left", 0)) *
                    (eb.get("bottom", 0) - eb.get("top", 0)))
            if area < best_area:
                best = el
                best_area = area
    return best


def _find_element_by_desc(desc: str, elements: list[dict]) -> dict | None:
    """Ищет элемент по desc/text — сначала точное совпадение, потом подстрока."""
    desc_lower = desc.lower()
    for el in elements:
        el_label = (el.get("desc") or el.get("text", "")).lower()
        if el_label and el_label == desc_lower:
            return el
    for el in elements:
        el_label = (el.get("desc") or el.get("text", "")).lower()
        if el_label and desc_lower in el_label:
            return el
    return None


def _resolve_element_ref(action: dict, elements: list[dict]) -> dict:
    """
    Резолвит ссылку на элемент в реальные id/desc/bounds.

    Стратегия поиска:
    1. По индексу #N / N из списка elements
    2. Fallback: по desc/text (если индекс невалидный)
    3. Если элемент не clickable — подбирает clickable-контейнер
    """
    node_id = action.get("node_id", "")
    desc = action.get("desc", "")
    el = None

    if node_id.startswith("#"):
        idx_str = node_id[1:]
    elif node_id.isdigit():
        idx_str = node_id
    else:
        idx_str = None

    if idx_str is not None:
        try:
            idx = int(idx_str)
            if 0 <= idx < len(elements):
                el = elements[idx]
            else:
                logger.warning(
                    f"[NAV] Element ref {node_id} out of range "
                    f"(0..{len(elements) - 1}), trying desc fallback"
                )
        except ValueError:
            logger.warning(f"[NAV] Cannot parse element ref: {node_id}")

    if el is None and desc:
        el = _find_element_by_desc(desc, elements)
        if el:
            logger.info(f"[NAV] Fallback: found element by desc={desc!r}")

    if el is None:
        if node_id and not idx_str:
            el = _find_element_by_desc(node_id, elements)
            if el:
                logger.info(f"[NAV] Fallback: found element by node_id as text={node_id!r}")

    if el is None:
        logger.warning(
            f"[NAV] Cannot resolve: node_id={node_id!r}, desc={desc!r} "
            f"— returning action unchanged"
        )
        return action

    if action.get("action") == "click" and not el.get("clickable"):
        container = _find_clickable_container(el, elements)
        if container:
            logger.info(
                f"[NAV] {node_id} not clickable, using container "
                f"id={container.get('id', '')!r} bounds={container.get('bounds')}"
            )
            el_desc = el.get("desc") or el.get("text", "")
            resolved = dict(action)
            resolved["node_id"] = container.get("id", "")
            if el_desc:
                resolved["desc"] = el_desc
            resolved["bounds"] = container.get("bounds") or el.get("bounds")
            return resolved

    resolved = dict(action)
    resolved["node_id"] = el.get("id", "")
    if el.get("desc"):
        resolved["desc"] = el["desc"]
    elif el.get("text"):
        resolved["desc"] = el["text"]
    if el.get("bounds"):
        resolved["bounds"] = el["bounds"]

    logger.info(
        f"[NAV] Resolved {node_id} → id={resolved.get('node_id')!r}, "
        f"desc={resolved.get('desc')!r}, bounds={resolved.get('bounds')}"
    )
    return resolved


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

    Резолвит ссылки #N из LLM-ответа в реальные id/desc/bounds элементов.
    """
    total_raw = _count_nodes(nodes)
    elements = _flatten_nodes(nodes)
    elements_text = _format_elements_for_prompt(elements)

    logger.info(
        f"[NAV] Step {step}: raw tree={total_raw} nodes, "
        f"flattened={len(elements)} elements"
    )
    for el in elements[:20]:
        logger.info(f"[NAV] ELEMENT: {el}")

    history = action_history or []
    history_text = _format_action_history(history)
    phase_hint = _get_phase_hint(history, step)

    user_text = NAV_USER_TEMPLATE.format(
        task_description=task_description,
        step=step,
        phase_hint=phase_hint,
        action_history=history_text,
        elements=elements_text,
    )

    user_content: list[dict] = []

    if screenshot_b64:
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{screenshot_b64}",
                "detail": "high",
            },
        })
        logger.info(f"[NAV] Step {step}: screenshot attached, {len(screenshot_b64)} chars base64")
    else:
        logger.warning(f"[NAV] Step {step}: no screenshot, text-only LLM call")

    user_content.append({"type": "text", "text": user_text})

    logger.info(
        f"[NAV] Step {step}: user_text={len(user_text)} chars, "
        f"model={model}, base_url={LLM_BASE_URL}"
    )

    for attempt in range(MAX_RETRY + 1):
        t0 = time.monotonic()
        logger.info(f"[NAV] Step {step}: LLM call attempt {attempt + 1}/{MAX_RETRY + 1}...")

        try:
            response = await _client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": NAV_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=512,
            )

            elapsed = time.monotonic() - t0
            raw = response.choices[0].message.content
            usage = getattr(response, "usage", None)
            logger.info(
                f"[NAV] Step {step}: LLM responded in {elapsed:.1f}s, "
                f"tokens={getattr(usage, 'total_tokens', '?') if usage else '?'}, "
                f"raw={raw[:500] if raw else 'EMPTY'}"
            )

            if not raw:
                logger.error(f"[NAV] Step {step}: LLM returned empty content!")
                if attempt < MAX_RETRY:
                    continue
                return {"action": "done", "reason": "LLM вернул пустой ответ"}

            parsed = _parse_llm_response(raw)
            if parsed:
                if parsed.get("action") in ("click", "type", "input_needed"):
                    parsed = _resolve_element_ref(parsed, elements)
                logger.info(f"[NAV] Step {step}: parsed action={parsed.get('action')}")
                return parsed

            if attempt < MAX_RETRY:
                logger.warning(
                    f"[NAV] Step {step}: invalid JSON (attempt {attempt + 1}), "
                    f"raw={raw[:300]}"
                )
                continue

            logger.error(
                f"[NAV] Step {step}: failed to parse after {MAX_RETRY + 1} attempts, "
                f"last raw={raw[:500]}"
            )
            return {"action": "done", "reason": "Не удалось разобрать ответ LLM"}

        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(
                f"[NAV] Step {step}: LLM call FAILED in {elapsed:.1f}s "
                f"(attempt {attempt + 1}): {type(e).__name__}: {e}",
                exc_info=True,
            )
            if attempt < MAX_RETRY:
                continue
            return {"action": "done", "reason": f"Ошибка LLM: {e}"}
