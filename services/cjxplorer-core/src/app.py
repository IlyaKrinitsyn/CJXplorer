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
    TaskInputRequest,
    TaskResponse,
    TaskStatus,
)
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
    """Создаёт задачу навигации. Android подключается к WS по task_id."""
    task = create_task(request.app_name, request.journey_description, request.model)
    task.status = TaskStatus.WAITING_DEVICE
    logger.info(f"Задача создана: {task.task_id} — {task.app_name}: {task.journey_description}")
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


@app.websocket("/ws/navigate/{task_id}")
async def ws_navigate(websocket: WebSocket, task_id: str):
    """WebSocket-эндпоинт для Android-устройства. Логика — в ws_handler."""
    task = get_task(task_id)
    if not task:
        await websocket.close(code=4004, reason="Task not found")
        return

    await handle_navigation_session(websocket, task)
