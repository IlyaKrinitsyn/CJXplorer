#!/usr/bin/env python3
"""
Фейк-Android клиент для тестирования WebSocket-навигации.

Имитирует поведение Android-устройства: подключается к WS,
получает команды от бэкенда и отвечает скриншотами + нодами.

Использование:
    # 1. Запустить бэкенд:
    cd services/cjxplorer-core && python run.py

    # 2. Создать задачу:
    curl -s -X POST http://localhost:8000/navigate \
        -H 'Content-Type: application/json' \
        -d '{"app_name": "Сбербанк", "journey_description": "Открыть вклад"}'

    # 3. Запустить фейк-клиент с одним скриншотом (отправляется на каждый шаг):
    python scripts/test_ws_client.py --task-id <id> --screenshot path/to/screen.png

    # 4. Или с папкой скриншотов (отправляются по порядку):
    python scripts/test_ws_client.py --task-id <id> --screenshots-dir ./test_screens/

    # 5. Или вообще без скриншотов (отправляется заглушка 1x1 px):
    python scripts/test_ws_client.py --task-id <id>

Зависимости:
    pip install websockets

Переменные окружения:
    WS_URL — базовый URL WebSocket (по умолчанию ws://localhost:8000)
"""

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Установите websockets: pip install websockets")
    raise SystemExit(1)


STUB_SCREENSHOT = base64.b64encode(
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
    b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
    b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
    b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
).decode("utf-8")

STUB_NODES = [
    {
        "id": "com.test:id/root",
        "class_name": "android.widget.FrameLayout",
        "text": "",
        "content_description": "",
        "bounds": {"left": 0, "top": 0, "right": 1080, "bottom": 2340},
        "clickable": False,
        "scrollable": False,
        "children": [
            {
                "id": "com.test:id/button_open",
                "class_name": "android.widget.Button",
                "text": "Открыть",
                "content_description": "Открыть вклад",
                "bounds": {"left": 100, "top": 500, "right": 980, "bottom": 600},
                "clickable": True,
                "scrollable": False,
                "children": [],
            },
            {
                "id": "com.test:id/scroll_view",
                "class_name": "android.widget.ScrollView",
                "text": "",
                "content_description": "",
                "bounds": {"left": 0, "top": 200, "right": 1080, "bottom": 2000},
                "clickable": False,
                "scrollable": True,
                "children": [],
            },
        ],
    }
]


def load_screenshots(screenshot_path: str | None, screenshots_dir: str | None) -> list[str]:
    """Загружает скриншоты из файла или папки, возвращает list[base64]."""
    if screenshots_dir:
        dir_path = Path(screenshots_dir)
        files = sorted(
            f for f in dir_path.iterdir()
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        )
        if not files:
            print(f"Папка {screenshots_dir} пуста, используем заглушку")
            return [STUB_SCREENSHOT]
        result = []
        for f in files:
            b64 = base64.b64encode(f.read_bytes()).decode("utf-8")
            result.append(b64)
            print(f"  Загружен: {f.name} ({len(b64)} chars)")
        return result

    if screenshot_path:
        b64 = base64.b64encode(Path(screenshot_path).read_bytes()).decode("utf-8")
        print(f"  Загружен: {screenshot_path} ({len(b64)} chars)")
        return [b64]

    print("  Скриншоты не указаны — используем заглушку (1x1 px)")
    return [STUB_SCREENSHOT]


def load_nodes(nodes_path: str | None) -> list[dict]:
    """Загружает ноды из JSON-файла или возвращает заглушку."""
    if nodes_path:
        data = json.loads(Path(nodes_path).read_text())
        print(f"  Ноды: {nodes_path} ({len(data)} корневых)")
        return data
    print("  Ноды: заглушка")
    return STUB_NODES


async def run_client(
    ws_url: str,
    task_id: str,
    screenshots: list[str],
    nodes: list[dict],
    max_steps: int,
):
    """Запускает фейк-клиент навигации."""
    uri = f"{ws_url}/ws/navigate/{task_id}"
    print(f"\nПодключение к {uri}...")

    async with websockets.connect(uri) as ws:
        print("Подключено!\n")

        step = 0
        async for raw_msg in ws:
            msg = json.loads(raw_msg)
            msg_type = msg.get("type")

            if msg_type == "start":
                print(f"[SERVER] start: {msg.get('task', '')}")

            elif msg_type == "action":
                action = msg.get("action", "?")
                print(f"[SERVER] action: {json.dumps(msg, ensure_ascii=False)}")

            elif msg_type == "input_needed":
                print(f"[SERVER] input_needed: {msg.get('prompt', '')}")
                print("  (фейк-клиент не поддерживает ввод, ждём input через REST)")
                continue

            elif msg_type == "done":
                print(f"\n[SERVER] done — навигация завершена")
                break

            elif msg_type == "input_response":
                print(f"[SERVER] input_response: node_id={msg.get('node_id')}")

            else:
                print(f"[SERVER] unknown: {msg}")

            step += 1
            if step > max_steps:
                print(f"\nЛимит шагов ({max_steps}) достигнут, отключаемся")
                break

            screenshot_idx = min(step - 1, len(screenshots) - 1)
            state = {
                "type": "state",
                "screenshot": screenshots[screenshot_idx],
                "nodes": nodes,
            }
            print(f"[CLIENT] step {step}: отправляю state "
                  f"(screenshot #{screenshot_idx + 1}, {len(nodes)} корневых нод)")
            await ws.send(json.dumps(state))

    print("\nОтключено.")

    print(f"\n--- Проверка статуса задачи ---")
    http_url = ws_url.replace("ws://", "http://").replace("wss://", "https://")
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"{http_url}/tasks/{task_id}")
        task_data = json.loads(resp.read())
        print(f"Статус: {task_data.get('status')}")
        print(f"Шагов: {task_data.get('current_step')}")
        if task_data.get("result"):
            print(f"Результат: {task_data['result'][:200]}...")
    except Exception as e:
        print(f"Не удалось получить статус: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Фейк-Android клиент для тестирования WebSocket-навигации"
    )
    parser.add_argument(
        "--task-id", required=True,
        help="ID задачи навигации (из POST /navigate)"
    )
    parser.add_argument(
        "--screenshot", "-s", default=None,
        help="Путь к скриншоту (отправляется на каждый шаг)"
    )
    parser.add_argument(
        "--screenshots-dir", "-d", default=None,
        help="Папка со скриншотами (отправляются по порядку)"
    )
    parser.add_argument(
        "--nodes", "-n", default=None,
        help="Путь к JSON-файлу с деревом нод (иначе — заглушка)"
    )
    parser.add_argument(
        "--ws-url", default=None,
        help="Базовый URL WebSocket (по умолчанию ws://localhost:8000)"
    )
    parser.add_argument(
        "--max-steps", type=int, default=20,
        help="Максимум шагов фейк-клиента (по умолчанию 20)"
    )
    args = parser.parse_args()

    ws_url = args.ws_url or os.getenv("WS_URL", "ws://localhost:8000")

    print("=== CJXplorer Fake Android Client ===")
    print(f"Task ID: {args.task_id}")
    print(f"WS URL: {ws_url}")
    print(f"Max steps: {args.max_steps}")

    screenshots = load_screenshots(args.screenshot, args.screenshots_dir)
    nodes = load_nodes(args.nodes)

    asyncio.run(run_client(ws_url, args.task_id, screenshots, nodes, args.max_steps))


if __name__ == "__main__":
    main()
