#!/usr/bin/env python3
"""
Изолированный тест навигационного агента.

Отправляет скриншот + дерево нод в decide_next_action()
и печатает ответ LLM. Позволяет быстро итерировать промпт
без запуска всего бэкенда или Android-устройства.

Использование:
    # С реальным скриншотом и нодами:
    python scripts/test_nav_agent.py \
        --screenshot path/to/screen.png \
        --nodes path/to/nodes.json \
        --task "Сбербанк: Открыть вклад"

    # Только скриншот (без нод):
    python scripts/test_nav_agent.py \
        --screenshot path/to/screen.png \
        --task "Сбербанк: Открыть вклад"

    # С историей предыдущих действий:
    python scripts/test_nav_agent.py \
        --screenshot path/to/screen.png \
        --nodes path/to/nodes.json \
        --task "Сбербанк: Открыть вклад" \
        --history '[{"action": "click", "node_id": "btn_1"}]'

Переменные окружения:
    LLM_API_KEY — обязательно
    LLM_BASE_URL — по умолчанию OpenRouter
    DEFAULT_MODEL — по умолчанию openai/gpt-4o
"""

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.nav_agent import decide_next_action  # noqa: E402


def load_screenshot(path: str) -> str:
    """Читает изображение и возвращает base64."""
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("utf-8")


def load_nodes(path: str) -> list[dict]:
    """Читает JSON-файл с деревом accessibility-нод."""
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(
        description="Тест навигационного агента (изолированный LLM-вызов)"
    )
    parser.add_argument(
        "--screenshot", "-s", required=True,
        help="Путь к скриншоту (PNG/JPEG)"
    )
    parser.add_argument(
        "--nodes", "-n", default=None,
        help="Путь к JSON-файлу с деревом accessibility-нод"
    )
    parser.add_argument(
        "--task", "-t", default="Сбербанк: Открыть вклад",
        help="Описание задачи (приложение: клиентский путь)"
    )
    parser.add_argument(
        "--step", type=int, default=1,
        help="Номер шага (по умолчанию 1)"
    )
    parser.add_argument(
        "--model", "-m", default=None,
        help="LLM-модель (по умолчанию из DEFAULT_MODEL)"
    )
    parser.add_argument(
        "--history", default=None,
        help="JSON-строка с историей действий (list[dict])"
    )
    args = parser.parse_args()

    if args.model is None:
        from src.config import DEFAULT_MODEL
        args.model = DEFAULT_MODEL

    print(f"Скриншот: {args.screenshot}")
    screenshot_b64 = load_screenshot(args.screenshot)
    print(f"  base64 длина: {len(screenshot_b64)}")

    nodes = []
    if args.nodes:
        nodes = load_nodes(args.nodes)
        print(f"Ноды: {args.nodes} ({len(nodes)} корневых)")
    else:
        print("Ноды: не предоставлены (пустой список)")

    action_history = []
    if args.history:
        action_history = json.loads(args.history)
        print(f"История: {len(action_history)} действий")

    print(f"Задача: {args.task}")
    print(f"Шаг: {args.step}")
    print(f"Модель: {args.model}")
    print("-" * 60)

    result = asyncio.run(decide_next_action(
        screenshot_b64=screenshot_b64,
        nodes=nodes,
        task_description=args.task,
        step=args.step,
        model=args.model,
        action_history=action_history,
    ))

    print("РЕЗУЛЬТАТ:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
