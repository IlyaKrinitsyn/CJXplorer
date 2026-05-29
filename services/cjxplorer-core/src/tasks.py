"""
Хранилище задач навигации (in-memory).

В MVP задачи хранятся в памяти процесса.
При рестарте теряются — для MVP это допустимо.

TODO: Перейти на persistent storage (PostgreSQL / SQLite)
      при выходе из MVP, чтобы задачи переживали рестарт.
      Скриншоты — в S3/MinIO.
"""

import asyncio
import uuid

from .models import TaskStatus


class NavigationTask:
    """Одна задача навигации по клиентскому пути."""

    def __init__(self, app_name: str, journey_description: str, model: str):
        self.task_id: str = uuid.uuid4().hex[:12]
        self.app_name = app_name
        self.journey_description = journey_description
        self.model = model
        self.status: TaskStatus = TaskStatus.PENDING
        self.current_step: int = 0
        self.screenshots: list[bytes] = []
        self.result: str | None = None
        self.action_history: list[dict] = []
        self.goals: list[dict] = []
        self.input_prompt: str | None = None
        self.input_event: asyncio.Event = asyncio.Event()
        self.input_value: str | None = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "app_name": self.app_name,
            "journey_description": self.journey_description,
            "current_step": self.current_step,
            "result": self.result,
            "input_prompt": self.input_prompt,
        }


TASKS: dict[str, NavigationTask] = {}
"""Глобальное хранилище задач по task_id."""


def create_task(app_name: str, journey_description: str, model: str) -> NavigationTask:
    """Создаёт новую задачу навигации."""
    task = NavigationTask(app_name, journey_description, model)
    TASKS[task.task_id] = task
    return task


def get_task(task_id: str) -> NavigationTask | None:
    """Возвращает задачу по ID или None."""
    return TASKS.get(task_id)
