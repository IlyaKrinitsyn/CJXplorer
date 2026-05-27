"""
Менеджер подключённых Android-устройств.

MVP: поддерживается одно устройство.
При создании задачи навигации уведомляет подключённое устройство
через постоянное WebSocket-соединение.
"""

import logging

from fastapi import WebSocket, WebSocketDisconnect

from .tasks import NavigationTask

logger = logging.getLogger(__name__)

_connected_device: WebSocket | None = None


async def handle_device_connection(websocket: WebSocket) -> None:
    """
    Обрабатывает постоянное WS-соединение устройства.
    Устройство подключается к /ws/device и ждёт уведомлений о новых задачах.
    """
    global _connected_device

    if _connected_device is not None:
        await websocket.close(code=4009, reason="Another device already connected")
        return

    await websocket.accept()
    _connected_device = websocket
    logger.info("Устройство подключено к /ws/device")

    try:
        await websocket.send_json({"type": "connected"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("Устройство отключилось от /ws/device")
    except Exception as e:
        logger.error(f"Device WS error: {e}")
    finally:
        _connected_device = None


def is_device_connected() -> bool:
    return _connected_device is not None


async def notify_new_task(task: NavigationTask) -> bool:
    """
    Уведомляет подключённое устройство о новой задаче навигации.
    Возвращает True, если уведомление отправлено.
    """
    if _connected_device is None:
        logger.warning(f"Задача {task.task_id}: устройство не подключено")
        return False

    try:
        await _connected_device.send_json({
            "type": "new_task",
            "task_id": task.task_id,
            "app_name": task.app_name,
            "journey_description": task.journey_description,
        })
        logger.info(f"Задача {task.task_id} отправлена на устройство")
        return True
    except Exception as e:
        logger.error(f"Не удалось отправить задачу на устройство: {e}")
        return False
