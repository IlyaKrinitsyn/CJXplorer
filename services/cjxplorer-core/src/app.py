"""
FastAPI-приложение бэкенда CJXplorer.

REST API для оценки скриншотов и управления задачами навигации.
WebSocket для связи с Android-устройством.
"""

import base64
import logging

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import AVAILABLE_MODELS, DEFAULT_MODEL, VERSION
from .eval_agent import evaluate_screenshots, suggest_improvements
from .models import (
    EvaluateRequest,
    EvaluateResponse,
    ImproveRequest,
    ImproveResponse,
    NavigateRequest,
    TaskEvaluateRequest,
    TaskInputRequest,
    TaskResponse,
    TaskScreenshotsResponse,
    TaskStatus,
)
from .device_manager import handle_device_connection, is_device_connected, notify_new_task
from .tasks import create_task, get_task
from .ws_handler import handle_navigation_session

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="CJXplorer Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Проверка работоспособности сервиса."""
    return {"status": "ok", "version": VERSION}


@app.get("/models")
async def list_models():
    """Возвращает список доступных LLM-моделей и модель по умолчанию."""
    return {"models": AVAILABLE_MODELS, "default": DEFAULT_MODEL}


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest):
    """Оценка клиентского пути по набору base64-скриншотов."""
    screenshots = [base64.b64decode(s) for s in request.screenshots]
    if not screenshots:
        raise HTTPException(400, "Нет скриншотов для оценки")

    try:
        result = await evaluate_screenshots(screenshots, request.model)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise HTTPException(500, f"Ошибка при анализе: {e}")

    return EvaluateResponse(result=result, model=request.model)


@app.post("/improve", response_model=ImproveResponse)
async def improve(request: ImproveRequest):
    """Анализ улучшений CJ: скриншоты + результат предыдущей оценки."""
    screenshots = [base64.b64decode(s) for s in request.screenshots]
    if not screenshots:
        raise HTTPException(400, "Нет скриншотов для анализа")

    try:
        result = await suggest_improvements(
            screenshots, request.evaluation_result, request.model
        )
    except Exception as e:
        logger.error(f"Improvement analysis failed: {e}")
        raise HTTPException(500, f"Ошибка при анализе улучшений: {e}")

    return ImproveResponse(result=result, model=request.model)


@app.post("/navigate", response_model=TaskResponse)
async def navigate(request: NavigateRequest):
    """Создаёт задачу навигации и уведомляет подключённое устройство."""
    task = create_task(request.app_name, request.journey_description, request.model)
    task.status = TaskStatus.WAITING_DEVICE
    logger.info(f"Задача создана: {task.task_id} — {task.app_name}: {task.journey_description}")

    await notify_new_task(task)

    return TaskResponse(**task.to_dict())


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """Возвращает текущий статус задачи навигации."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    return TaskResponse(**task.to_dict())


@app.post("/tasks/{task_id}/input", response_model=TaskResponse)
async def provide_input(task_id: str, request: TaskInputRequest):
    """Передаёт пользовательский ввод (логин, пароль, код) в задачу навигации."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    if task.status != TaskStatus.INPUT_NEEDED:
        raise HTTPException(400, "Задача не ожидает ввода")

    task.input_value = request.value
    task.input_event.set()
    return TaskResponse(**task.to_dict())


@app.get("/tasks/{task_id}/screenshots", response_model=TaskScreenshotsResponse)
async def get_task_screenshots(task_id: str):
    """Возвращает скриншоты навигационной задачи из runtime-кеша."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    if task.status not in (TaskStatus.DONE, TaskStatus.EVALUATING, TaskStatus.FAILED):
        raise HTTPException(400, f"Навигация ещё не завершена (статус: {task.status.value})")

    screenshots_b64 = [
        base64.b64encode(s).decode("utf-8") for s in task.screenshots
    ]
    return TaskScreenshotsResponse(
        task_id=task_id,
        screenshots=screenshots_b64,
        count=len(screenshots_b64),
    )


@app.post("/tasks/{task_id}/evaluate", response_model=EvaluateResponse)
async def evaluate_task(task_id: str, request: TaskEvaluateRequest):
    """Оценка CJ из кеша навигационной задачи (без повторной отправки скриншотов)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    if not task.screenshots:
        raise HTTPException(400, "Нет скриншотов для оценки")

    task.status = TaskStatus.EVALUATING
    try:
        result = await evaluate_screenshots(task.screenshots, request.model)
        task.result = result
        task.status = TaskStatus.DONE
    except Exception as e:
        logger.error(f"Task {task_id} evaluation failed: {e}")
        task.status = TaskStatus.DONE
        raise HTTPException(500, f"Ошибка при анализе: {e}")

    return EvaluateResponse(result=result, model=request.model)


@app.post("/tasks/{task_id}/improve", response_model=ImproveResponse)
async def improve_task(task_id: str, request: TaskEvaluateRequest):
    """Рекомендации по улучшению CJ из кеша навигационной задачи."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    if not task.screenshots:
        raise HTTPException(400, "Нет скриншотов для анализа")
    if not task.result:
        raise HTTPException(400, "Сначала выполните оценку (POST /tasks/{task_id}/evaluate)")

    try:
        result = await suggest_improvements(
            task.screenshots, task.result, request.model
        )
    except Exception as e:
        logger.error(f"Task {task_id} improvement failed: {e}")
        raise HTTPException(500, f"Ошибка при анализе улучшений: {e}")

    return ImproveResponse(result=result, model=request.model)


@app.get("/device/status")
async def device_status():
    """Проверяет, подключено ли Android-устройство."""
    return {"connected": is_device_connected()}


@app.websocket("/ws/device")
async def ws_device(websocket: WebSocket):
    """Постоянное WS-соединение Android-устройства для получения новых задач."""
    await handle_device_connection(websocket)


@app.websocket("/ws/navigate/{task_id}")
async def ws_navigate(websocket: WebSocket, task_id: str):
    """WebSocket-эндпоинт для навигационной сессии. Логика — в ws_handler."""
    task = get_task(task_id)
    if not task:
        await websocket.close(code=4004, reason="Task not found")
        return

    await handle_navigation_session(websocket, task)
