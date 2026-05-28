"""
Обработчик WebSocket-сессии навигации.

Управляет циклом взаимодействия с Android-устройством:
получение состояния экрана -> решение LLM -> отправка действия.

После завершения навигации скриншоты остаются в кеше задачи (task.screenshots).
Оценку запускает пользователь через REST API.
"""

import asyncio
import base64
import json
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect

from .config import NAV_MAX_STEPS
from .device_manager import set_device_busy, set_device_available
from .models import TaskStatus
from .nav_agent import decide_next_action
from .tasks import NavigationTask

logger = logging.getLogger(__name__)

MAX_REPEAT_ACTIONS = 3


def _detect_loop(action_history: list[dict]) -> bool:
    """
    Определяет зацикливание: одинаковое действие повторяется
    MAX_REPEAT_ACTIONS раз подряд.
    Сравнивает action + node_id + direction (без reason — он меняется).
    """
    if len(action_history) < MAX_REPEAT_ACTIONS:
        return False

    def _key(a: dict) -> tuple:
        return (a.get("action"), a.get("node_id"), a.get("direction"))

    recent = action_history[-MAX_REPEAT_ACTIONS:]
    return all(_key(a) == _key(recent[0]) for a in recent)


async def handle_navigation_session(websocket: WebSocket, task: NavigationTask) -> None:
    """
    Основной цикл навигации по клиентскому пути.

    Протокол:
    1. Бэк отправляет start с описанием задачи
    2. Android отвечает state (скриншот + дерево нод)
    3. Бэк анализирует через LLM и отправляет action
    4. Повтор до done или лимита шагов

    При необходимости ввода данных (логин/пароль) —
    ставит задачу на паузу и ждёт input от пользователя через REST API.

    По завершении скриншоты остаются в task.screenshots для последующей оценки.
    """
    await websocket.accept()
    task.status = TaskStatus.RUNNING
    set_device_busy(task.task_id)
    logger.info(f"[WS] Устройство подключено к задаче {task.task_id}")

    try:
        if task.app_name:
            task_text = f"Открой приложение {task.app_name} и выполни: {task.journey_description}"
        else:
            task_text = task.journey_description

        start_msg = {"type": "start", "task": task_text}
        logger.info(f"[WS→device] Отправка start: {json.dumps(start_msg, ensure_ascii=False)[:300]}")
        await websocket.send_json(start_msg)

        while task.current_step < NAV_MAX_STEPS:
            logger.info(f"[WS] Ожидание state от устройства (шаг {task.current_step + 1})...")
            data = await websocket.receive_json()

            msg_type = data.get("type", "unknown")
            logger.info(
                f"[WS←device] Получено: type={msg_type}, "
                f"screenshot={len(data.get('screenshot', ''))} chars, "
                f"nodes={len(data.get('nodes', []))} items, "
                f"полный размер={len(json.dumps(data))} chars"
            )

            if msg_type != "state":
                logger.warning(f"[WS] Пропускаем сообщение type={msg_type}")
                continue

            task.current_step += 1
            screenshot_b64 = data.get("screenshot", "")
            nodes = data.get("nodes", [])

            if screenshot_b64:
                task.screenshots.append(base64.b64decode(screenshot_b64))
                logger.info(f"[WS] Скриншот сохранён: {len(screenshot_b64)} chars base64")
            else:
                logger.warning(f"[WS] Пустой скриншот на шаге {task.current_step}")

            if task.app_name:
                task_desc = f"{task.app_name}: {task.journey_description}"
            else:
                task_desc = task.journey_description

            logger.info(
                f"[WS] Вызов LLM: шаг={task.current_step}, "
                f"модель={task.model}, screenshot={len(screenshot_b64)} chars, "
                f"nodes={len(nodes)} items, history={len(task.action_history)} actions"
            )
            llm_start = time.monotonic()

            try:
                action = await decide_next_action(
                    screenshot_b64=screenshot_b64,
                    nodes=nodes,
                    task_description=task_desc,
                    step=task.current_step,
                    model=task.model,
                    action_history=task.action_history,
                )
            except Exception as e:
                logger.error(
                    f"[WS] LLM вызов упал через {time.monotonic() - llm_start:.1f}s: "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )
                await websocket.send_json({
                    "type": "done",
                    "reason": f"LLM error: {e}",
                })
                task.status = TaskStatus.FAILED
                task.result = f"LLM error: {e}"
                return

            llm_elapsed = time.monotonic() - llm_start
            logger.info(
                f"[WS] LLM ответил за {llm_elapsed:.1f}s: "
                f"{json.dumps(action, ensure_ascii=False)[:500]}"
            )

            task.action_history.append(action)

            if _detect_loop(task.action_history):
                logger.warning(
                    f"[WS] Обнаружен цикл на шаге {task.current_step}, "
                    f"принудительное завершение"
                )
                await websocket.send_json({"type": "done"})
                task.result = "Навигация зациклилась — одни и те же действия повторяются"
                break

            if action.get("action") == "done":
                logger.info(f"[WS→device] Отправка done")
                await websocket.send_json({"type": "done"})
                break

            if action.get("action") == "input_needed":
                await _handle_input_request(websocket, task, action)
                continue

            out_msg = {"type": "action", **action}
            logger.info(
                f"[WS→device] Отправка action: "
                f"{json.dumps(out_msg, ensure_ascii=False)[:500]}"
            )
            await websocket.send_json(out_msg)

        logger.info(
            f"[WS] Задача {task.task_id}: навигация завершена, "
            f"{len(task.screenshots)} скриншотов в кеше"
        )
        task.status = TaskStatus.DONE

    except WebSocketDisconnect:
        logger.warning(f"[WS] Устройство отключилось от задачи {task.task_id}")
        task.status = TaskStatus.FAILED
        task.result = "Устройство отключилось"
    except asyncio.TimeoutError:
        logger.warning(f"[WS] Задача {task.task_id}: таймаут ожидания ввода")
        task.status = TaskStatus.FAILED
        task.result = "Таймаут ожидания ввода данных"
    except Exception as e:
        logger.error(f"[WS] Задача {task.task_id} упала: {type(e).__name__}: {e}", exc_info=True)
        task.status = TaskStatus.FAILED
        task.result = str(e)
    finally:
        set_device_available()


async def _handle_input_request(
    websocket: WebSocket, task: NavigationTask, action: dict
) -> None:
    """
    Обрабатывает запрос ввода данных от пользователя.

    Ставит задачу на паузу (INPUT_NEEDED), ждёт пока пользователь
    передаст данные через REST API, затем пробрасывает на устройство.
    Таймаут — 5 минут.
    """
    task.status = TaskStatus.INPUT_NEEDED
    task.input_prompt = action.get("prompt", "Требуется ввод данных")
    task.input_event.clear()

    await websocket.send_json({
        "type": "input_needed",
        "prompt": task.input_prompt,
    })

    await asyncio.wait_for(task.input_event.wait(), timeout=300)

    task.status = TaskStatus.RUNNING
    await websocket.send_json({
        "type": "input_response",
        "node_id": action.get("node_id", ""),
        "value": task.input_value,
    })
    task.input_prompt = None
    task.input_value = None
