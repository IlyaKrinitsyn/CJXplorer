"""
Pydantic-модели для API запросов/ответов и WebSocket-протокола.

Определяет контракты между бэкендом, Telegram-ботом и Android-устройством.
"""

from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Статусы задачи навигации по клиентскому пути."""
    PENDING = "pending"
    WAITING_DEVICE = "waiting_device"
    RUNNING = "running"
    INPUT_NEEDED = "input_needed"
    EVALUATING = "evaluating"
    DONE = "done"
    FAILED = "failed"


class EvaluateRequest(BaseModel):
    """Запрос на оценку CJ по скриншотам."""
    screenshots: list[str] = Field(
        ..., description="Скриншоты в формате base64", min_length=1
    )
    model: str = Field(
        "openai/gpt-4o", description="Идентификатор LLM-модели для оценки"
    )


class EvaluateResponse(BaseModel):
    """Ответ с результатом оценки клиентского пути."""
    result: str = Field(..., description="Текст оценки от LLM")
    model: str = Field(..., description="Модель, которая выполнила оценку")


class NavigateRequest(BaseModel):
    """Запрос на создание задачи автономной навигации."""
    app_name: str = Field(
        ..., description="Название приложения (например, 'Сбербанк')"
    )
    journey_description: str = Field(
        ..., description="Описание клиентского пути (например, 'Открыть вклад')"
    )
    model: str = Field(
        "openai/gpt-4o", description="Идентификатор LLM-модели для навигации"
    )


class TaskResponse(BaseModel):
    """Ответ со статусом задачи навигации."""
    task_id: str = Field(..., description="Уникальный идентификатор задачи")
    status: TaskStatus = Field(..., description="Текущий статус задачи")
    app_name: str = Field(..., description="Название приложения")
    journey_description: str = Field(..., description="Описание клиентского пути")
    current_step: int = Field(0, description="Номер текущего шага навигации")
    result: str | None = Field(
        None, description="Результат оценки (заполняется при status=done)"
    )
    input_prompt: str | None = Field(
        None,
        description="Текст запроса ввода от пользователя (при status=input_needed)",
    )


class TaskInputRequest(BaseModel):
    """Пользователь предоставляет запрошенные данные (логин, пароль, код и т.д.)."""
    value: str = Field(..., description="Значение, введённое пользователем")


# --- WebSocket-протокол ---


class WSMessageType(str, Enum):
    """Типы сообщений WebSocket-протокола между бэкендом и Android."""
    START = "start"
    STATE = "state"
    ACTION = "action"
    INPUT_NEEDED = "input_needed"
    INPUT_RESPONSE = "input_response"
    DONE = "done"
    ERROR = "error"


class Bounds(BaseModel):
    """Координаты прямоугольника элемента UI на экране Android."""
    left: int = Field(..., description="Левая граница (px)")
    top: int = Field(..., description="Верхняя граница (px)")
    right: int = Field(..., description="Правая граница (px)")
    bottom: int = Field(..., description="Нижняя граница (px)")


class AccessibilityNode(BaseModel):
    """Нода дерева AccessibilityService Android-устройства."""
    id: str = Field(..., description="Уникальный идентификатор ноды")
    class_name: str = Field("", description="Android class (например, android.widget.Button)")
    text: str = Field("", description="Текст элемента")
    content_description: str = Field("", description="contentDescription для accessibility")
    bounds: Bounds = Field(..., description="Координаты элемента на экране")
    clickable: bool = Field(False, description="Элемент кликабелен")
    scrollable: bool = Field(False, description="Элемент поддерживает скролл")
    children: list["AccessibilityNode"] = Field(
        default_factory=list, description="Дочерние ноды"
    )
