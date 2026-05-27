"""
Обработчик WebSocket-сессии навигации.

Управляет циклом взаимодействия с Android-устройством:
получение состояния экрана -> решение LLM -> отправка действия.

После завершения навигации скриншоты остаются в кеше задачи (task.screenshots).
Оценку запускает пользователь через REST API.
"""

import asyncio
import base64
import logging

from fastapi import WebSocket, WebSocketDisconnect

from .config import NAV_MAX_STEPS
from .models import TaskStatus
from .nav_agent import decide_next_action
from .tasks import NavigationTask

logger = logging.getLogger(__name__)


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
    logger.info(f"Устройство подключено к задаче {task.task_id}")

    try:
        if task.app_name:
            task_text = f"Открой приложение {task.app_name} и выполни: {task.journey_description}"
        else:
            task_text = task.journey_description

        await websocket.send_json({
            "type": "start",
            "task": task_text,
        })

        while task.current_step < NAV_MAX_STEPS:
            data = await websocket.receive_json()

            if data.get("type") != "state":
                continue

            task.current_step += 1
            screenshot_b64 = data.get("screenshot", "")
            nodes = data.get("nodes", [])

            if screenshot_b64:
                task.screenshots.append(base64.b64decode(screenshot_b64))

            if task.app_name:
                task_desc = f"{task.app_name}: {task.journey_description}"
            else:
                task_desc = task.journey_description

            action = await decide_next_action(
                screenshot_b64=screenshot_b64,
                nodes=nodes,
                task_description=task_desc,
                step=task.current_step,
                model=task.model,
                action_history=task.action_history,
            )

            task.action_history.append(action)

            if action.get("action") == "done":
                await websocket.send_json({"type": "done"})
                break

            if action.get("action") == "input_needed":
                await _handle_input_request(websocket, task, action)
                continue

            await websocket.send_json({"type": "action", **action})

        logger.info(
            f"Задача {task.task_id}: навигация завершена, "
            f"{len(task.screenshots)} скриншотов в кеше"
        )
        task.status = TaskStatus.DONE

    except WebSocketDisconnect:
        logger.warning(f"Устройство отключилось от задачи {task.task_id}")
        task.status = TaskStatus.FAILED
        task.result = "Устройство отключилось"
    except asyncio.TimeoutError:
        logger.warning(f"Задача {task.task_id}: таймаут ожидания ввода")
        task.status = TaskStatus.FAILED
        task.result = "Таймаут ожидания ввода данных"
    except Exception as e:
        logger.error(f"Задача {task.task_id} упала: {e}")
        task.status = TaskStatus.FAILED
        task.result = str(e)


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
