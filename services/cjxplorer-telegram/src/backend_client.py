"""
HTTP-клиент для обращения к бэкенду CJXplorer.

Использует ленивую инициализацию httpx.AsyncClient
и корректно закрывает соединение при завершении бота.
"""

import base64

import httpx

from .config import BACKEND_URL

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Возвращает httpx-клиент, создавая при первом вызове."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=120.0)
    return _client


async def close() -> None:
    """Закрывает httpx-клиент. Вызывается при завершении бота."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def get_backend_version() -> str:
    """Получить версию бэкенда."""
    try:
        resp = await _get_client().get("/health")
        resp.raise_for_status()
        return resp.json().get("version", "?")
    except Exception:
        return "?"


async def get_models() -> dict:
    """Получить список доступных моделей с бэкенда."""
    resp = await _get_client().get("/models")
    resp.raise_for_status()
    return resp.json()


async def evaluate(screenshots: list[bytes], model: str) -> dict:
    """Отправить скриншоты на оценку и получить результат."""
    payload = {
        "screenshots": [base64.b64encode(s).decode() for s in screenshots],
        "model": model,
    }
    resp = await _get_client().post("/evaluate", json=payload)
    resp.raise_for_status()
    return resp.json()


async def improve(
    screenshots: list[bytes], evaluation_result: str, model: str
) -> dict:
    """Отправить скриншоты и результат оценки на анализ улучшений."""
    payload = {
        "screenshots": [base64.b64encode(s).decode() for s in screenshots],
        "evaluation_result": evaluation_result,
        "model": model,
    }
    resp = await _get_client().post("/improve", json=payload)
    resp.raise_for_status()
    return resp.json()


async def create_navigation_task(app_name: str, journey: str, model: str) -> dict:
    """Создать задачу навигации на бэкенде."""
    payload = {
        "app_name": app_name,
        "journey_description": journey,
        "model": model,
    }
    resp = await _get_client().post("/navigate", json=payload)
    resp.raise_for_status()
    return resp.json()


async def get_task_status(task_id: str) -> dict:
    """Получить текущий статус задачи навигации."""
    resp = await _get_client().get(f"/tasks/{task_id}")
    resp.raise_for_status()
    return resp.json()


async def provide_task_input(task_id: str, value: str) -> dict:
    """Передать пользовательские данные (логин, пароль и т.д.) в задачу."""
    resp = await _get_client().post(f"/tasks/{task_id}/input", json={"value": value})
    resp.raise_for_status()
    return resp.json()
