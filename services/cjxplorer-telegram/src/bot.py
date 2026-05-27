"""
Telegram-бот CJXplorer.

Принимает скриншоты клиентского пути от пользователя,
отправляет их на оценку через бэкенд и возвращает результат.
Поддерживает режим исследования CJ — автономный проход на Android.

Весь флоу (загрузка -> анализ -> результат) происходит
в одном редактируемом сообщении.
"""

import asyncio
import base64
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import TELEGRAM_BOT_TOKEN, VERSION
from . import backend_client

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SESSIONS: dict[int, list[bytes]] = {}
"""Хранилище загруженных скриншотов по chat_id."""

STATUS_MESSAGES: dict[int, int] = {}
"""ID статусного сообщения для каждого чата."""

USER_MODELS: dict[int, str] = {}
"""Выбранная модель для каждого чата."""

LAST_EVALUATIONS: dict[int, dict] = {}
"""Результат последней оценки для каждого чата (screenshots + result + model)."""

NAV_SESSIONS: dict[int, dict] = {}
"""Состояние навигационной сессии по chat_id.
Ключи: state, task_id, query, poll_task.
state: awaiting_query | polling | done
"""

_MODELS_CACHE: dict | None = None
_MODELS_CACHE_TS: float = 0.0
_MODELS_CACHE_TTL: float = 300.0

_FALLBACK_MODELS: dict = {
    "models": {"openai/gpt-4o": "GPT-4o"},
    "default": "openai/gpt-4o",
}

NAV_POLL_INTERVAL = 3.0


async def _get_models() -> dict:
    """Получает список моделей с бэкенда (с кешированием и TTL 5 мин)."""
    global _MODELS_CACHE, _MODELS_CACHE_TS
    now = time.monotonic()
    if _MODELS_CACHE is not None and (now - _MODELS_CACHE_TS) < _MODELS_CACHE_TTL:
        return _MODELS_CACHE
    try:
        data = await backend_client.get_models()
        _MODELS_CACHE = data
        _MODELS_CACHE_TS = now
    except Exception:
        if _MODELS_CACHE is not None:
            return _MODELS_CACHE
        return _FALLBACK_MODELS
    return _MODELS_CACHE


async def _available_models() -> dict[str, str]:
    data = await _get_models()
    return data["models"]


async def _default_model() -> str:
    data = await _get_models()
    return data["default"]


def _pluralize(n: int, one: str, few: str, many: str) -> str:
    if 11 <= n % 100 <= 19:
        return f"{n} {many}"
    mod = n % 10
    if mod == 1:
        return f"{n} {one}"
    if 2 <= mod <= 4:
        return f"{n} {few}"
    return f"{n} {many}"


def _screenshots_label(count: int) -> str:
    return _pluralize(count, "скриншот", "скриншота", "скриншотов")


async def _get_model(chat_id: int) -> str:
    return USER_MODELS.get(chat_id, await _default_model())


async def _model_label(model_id: str) -> str:
    models = await _available_models()
    return models.get(model_id, model_id)


# --- Клавиатуры ---


KB_START = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📸 Оценка CJ", callback_data="mode_evaluate"),
        InlineKeyboardButton("🔍 Исследование CJ", callback_data="nav_start"),
    ]
])

KB_AFTER_EVAL = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("💡 Как улучшить?", callback_data="improve"),
        InlineKeyboardButton("🔄 Новая оценка", callback_data="new_session"),
    ]
])

KB_NEW_SESSION = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔄 Новая оценка", callback_data="new_session")]
])

KB_NAV_CANCEL = InlineKeyboardMarkup([
    [InlineKeyboardButton("❌ Отмена", callback_data="nav_cancel")]
])


async def _kb_after_screenshot(chat_id: int) -> InlineKeyboardMarkup:
    model = await _get_model(chat_id)
    label = await _model_label(model)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Оценить", callback_data="evaluate"),
            InlineKeyboardButton("🗑 Сбросить", callback_data="reset"),
        ],
        [
            InlineKeyboardButton(
                f"🔀 Модель: {label}", callback_data="pick_model"
            ),
        ],
        [InlineKeyboardButton("← В начало", callback_data="go_home")],
    ])


async def _kb_model_picker() -> InlineKeyboardMarkup:
    models = await _available_models()
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"model:{model_id}")]
        for model_id, label in models.items()
    ]
    buttons.append([InlineKeyboardButton("« Назад", callback_data="back_to_status")])
    return InlineKeyboardMarkup(buttons)


# --- Утилиты сообщений ---


async def _send_or_edit(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE,
                        reply_markup=None, parse_mode=None, edit: bool = True) -> None:
    from telegram.error import BadRequest

    for mode in ([parse_mode, None] if parse_mode else [None]):
        if edit and chat_id in STATUS_MESSAGES:
            try:
                await context.bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=STATUS_MESSAGES[chat_id],
                    reply_markup=reply_markup,
                    parse_mode=mode,
                )
                return
            except BadRequest as e:
                if "can't parse entities" in str(e).lower() and mode is not None:
                    continue
            except Exception:
                break
        break

    for mode in ([parse_mode, None] if parse_mode else [None]):
        try:
            msg = await context.bot.send_message(
                chat_id, text, reply_markup=reply_markup, parse_mode=mode
            )
            STATUS_MESSAGES[chat_id] = msg.message_id
            return
        except BadRequest as e:
            if "can't parse entities" in str(e).lower() and mode is not None:
                continue
            raise


async def _edit_status(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE,
                       reply_markup=None, parse_mode=None) -> None:
    await _send_or_edit(chat_id, text, context, reply_markup, parse_mode, edit=True)


async def _status_text(chat_id: int) -> str:
    count = len(SESSIONS.get(chat_id, []))
    model = await _model_label(await _get_model(chat_id))
    return (
        f"📎 Загружено: {_screenshots_label(count)}\n"
        f"🤖 Модель: {model}\n\n"
        f"Можешь отправить ещё скриншоты или нажми «Оценить», когда все загружены."
    )


async def _build_footer(label: str) -> str:
    core_version = await backend_client.get_backend_version()
    return (
        f"\n\n🤖 <i>Модель: {label}</i>"
        f"\n<i>core=v{core_version} · telegram=v{VERSION}</i>"
    )


async def _send_chunked(chat_id: int, result: str, footer: str,
                        context: ContextTypes.DEFAULT_TYPE,
                        reply_markup=None, edit_first: bool = True) -> None:
    result_with_footer = result + footer
    if len(result_with_footer) <= 4096:
        if edit_first:
            await _edit_status(
                chat_id, result_with_footer, context,
                reply_markup=reply_markup, parse_mode="HTML",
            )
        else:
            await _send_or_edit(
                chat_id, result_with_footer, context,
                reply_markup=reply_markup, parse_mode="HTML", edit=False,
            )
    else:
        chunks = [result[i: i + 4096] for i in range(0, len(result), 4096)]
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            if is_last:
                chunk += footer
            if i == 0 and edit_first:
                await _edit_status(
                    chat_id, chunk, context, parse_mode="HTML",
                    reply_markup=reply_markup if is_last else None,
                )
            else:
                await _send_or_edit(
                    chat_id, chunk, context, parse_mode="HTML",
                    reply_markup=reply_markup if is_last else None,
                    edit=False,
                )


async def _refresh_status_below(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаляет старое статусное сообщение и создаёт новое ниже последнего скриншота."""
    old_msg_id = STATUS_MESSAGES.pop(chat_id, None)
    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id, old_msg_id)
        except Exception:
            pass
    await _send_or_edit(
        chat_id, await _status_text(chat_id),
        context, reply_markup=await _kb_after_screenshot(chat_id),
        edit=False,
    )


async def _remove_buttons(query) -> None:
    """Убирает кнопки с сообщения, на котором нажали."""
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


# --- /start ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    SESSIONS.pop(chat_id, None)
    STATUS_MESSAGES.pop(chat_id, None)
    LAST_EVALUATIONS.pop(chat_id, None)
    nav = NAV_SESSIONS.pop(chat_id, None)
    if nav and "poll_task" in nav:
        nav["state"] = "cancelled"
        nav["poll_task"].cancel()

    await update.message.reply_text(
        "Привет! Я оцениваю клиентские пути по критериальной модели CX.\n\n"
        "📸 <b>Оценка CJ</b> — отправь скриншоты и получи оценку.\n"
        "🔍 <b>Исследование CJ</b> — автоматический проход пути на Android.\n\n"
        "Выбери режим работы:",
        parse_mode="HTML",
        reply_markup=KB_START,
    )


# --- Оценка скриншотов ---


async def _save_screenshot(chat_id: int, data: bytes) -> int:
    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = []
    SESSIONS[chat_id].append(data)
    return len(SESSIONS[chat_id])


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    await _save_screenshot(chat_id, bytes(data))
    await _refresh_status_below(chat_id, context)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Отправь изображение (скриншот экрана).")
        return

    chat_id = update.effective_chat.id
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    await _save_screenshot(chat_id, bytes(data))
    await _refresh_status_below(chat_id, context)


async def _do_evaluate(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    screenshots = SESSIONS.get(chat_id, [])
    if not screenshots:
        await _edit_status(
            chat_id, "Нет загруженных скриншотов. Сначала отправь скрины CJ.", context
        )
        return

    model = await _get_model(chat_id)
    label = await _model_label(model)

    await _edit_status(
        chat_id,
        f"⏳ Анализирую {_screenshots_label(len(screenshots))} на {label}…",
        context,
    )

    try:
        data = await backend_client.evaluate(screenshots, model)
        result = data["result"]
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        await _edit_status(chat_id, f"Ошибка при анализе: {e}", context)
        return

    LAST_EVALUATIONS[chat_id] = {
        "screenshots": screenshots,
        "result": result,
        "model": model,
    }

    footer = await _build_footer(label)
    await _send_chunked(chat_id, result, footer, context, reply_markup=KB_AFTER_EVAL)
    SESSIONS.pop(chat_id, None)


async def _do_improve(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    last = LAST_EVALUATIONS.get(chat_id)
    if not last:
        await _send_or_edit(
            chat_id,
            "Нет данных для анализа улучшений. Сначала проведи оценку.",
            context, edit=False,
        )
        return

    model = last["model"]
    label = await _model_label(model)

    await _send_or_edit(
        chat_id,
        f"💡 Анализирую возможные улучшения на {label}…",
        context, edit=False,
    )

    try:
        data = await backend_client.improve(
            last["screenshots"], last["result"], model
        )
        result = data["result"]
    except Exception as e:
        logger.error(f"Improvement analysis failed: {e}")
        await _send_or_edit(
            chat_id, f"Ошибка при анализе улучшений: {e}", context, edit=False,
        )
        return

    footer = await _build_footer(label)
    await _send_chunked(
        chat_id, result, footer, context,
        reply_markup=KB_NEW_SESSION, edit_first=False,
    )
    LAST_EVALUATIONS.pop(chat_id, None)


# --- Исследование CJ ---


def _nav_status_text(nav: dict) -> str:
    status = nav.get("status", "?")
    step = nav.get("current_step", 0)
    query = nav.get("query", "?")

    status_labels = {
        "waiting_device": "⏳ Ожидание устройства…",
        "running": f"🔄 Исследование… (шаг {step})",
        "input_needed": "⌨️ Требуется ввод данных",
        "evaluating": "📊 Оценка результатов…",
        "done": "✅ Исследование завершено",
        "failed": "❌ Ошибка исследования",
    }
    status_text = status_labels.get(status, status)

    return (
        f"🔍 <b>Исследование CJ</b>\n\n"
        f"📋 {query}\n\n"
        f"{status_text}"
    )


async def _nav_start(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начинает исследование CJ — проверяет устройство и просит описать задачу."""
    device_connected = await backend_client.get_device_status()

    if not device_connected:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Попробовать снова", callback_data="nav_start")],
            [
                InlineKeyboardButton("📸 Оценка CJ", callback_data="mode_evaluate"),
                InlineKeyboardButton("← В начало", callback_data="go_home"),
            ],
        ])
        await _send_or_edit(
            chat_id,
            "🔍 <b>Исследование CJ</b>\n\n"
            "⚠️ Android-устройство не подключено.\n"
            "Запусти приложение CJXplorer на телефоне и попробуй снова.",
            context, parse_mode="HTML", edit=False,
            reply_markup=kb,
        )
        return

    NAV_SESSIONS[chat_id] = {"state": "awaiting_query"}
    await _send_or_edit(
        chat_id,
        "🔍 <b>Исследование CJ</b>\n\n"
        "Опиши, какой клиентский путь исследовать и в каком приложении.\n\n"
        "<i>Например:\n"
        "• Покупка мандаринов в Яндекс.Еда\n"
        "• Открытие вклада в Сбербанк\n"
        "• Оформление ОСАГО в Тинькофф</i>\n\n"
        "⚠️ Пока поддерживается <b>один клиентский путь в одном приложении</b>. "
        "Сравнительный анализ нескольких приложений — в следующих версиях.\n\n"
        "🚧 <i>Разработка в процессе</i>",
        context, parse_mode="HTML", edit=False,
        reply_markup=KB_NAV_CANCEL,
    )


async def _nav_handle_text(chat_id: int, text: str,
                           context: ContextTypes.DEFAULT_TYPE) -> None:
    nav = NAV_SESSIONS.get(chat_id)
    if not nav:
        return

    if nav["state"] != "awaiting_query":
        return

    nav["query"] = text
    nav["state"] = "polling"
    model = await _get_model(chat_id)

    await _send_or_edit(
        chat_id,
        f"🔍 <b>Исследование CJ</b>\n\n"
        f"📋 {text}\n\n"
        f"⏳ Создаю задачу…",
        context, parse_mode="HTML", edit=False,
    )

    try:
        task_data = await backend_client.create_navigation_task(
            "", text, model
        )
        nav["task_id"] = task_data["task_id"]
        nav["model"] = model
    except Exception as e:
        logger.error(f"Failed to create nav task: {e}")
        await _send_or_edit(
            chat_id, f"Ошибка при создании задачи: {e}",
            context, edit=False,
        )
        NAV_SESSIONS.pop(chat_id, None)
        return

    poll_task = asyncio.create_task(
        _poll_navigation(chat_id, context)
    )
    nav["poll_task"] = poll_task


async def _poll_navigation(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    nav = NAV_SESSIONS.get(chat_id)
    if not nav or "task_id" not in nav:
        return

    task_id = nav["task_id"]
    last_status = ""
    last_step = -1

    try:
        while True:
            await asyncio.sleep(NAV_POLL_INTERVAL)

            nav = NAV_SESSIONS.get(chat_id)
            if not nav or nav.get("state") == "cancelled":
                return

            try:
                task_data = await backend_client.get_task_status(task_id)
            except Exception as e:
                logger.error(f"Poll error for task {task_id}: {e}")
                continue

            status = task_data.get("status", "?")
            step = task_data.get("current_step", 0)

            if status != last_status or step != last_step:
                last_status = status
                last_step = step
                nav["status"] = status
                nav["current_step"] = step

                try:
                    await _edit_status(
                        chat_id, _nav_status_text(nav), context,
                        parse_mode="HTML",
                        reply_markup=KB_NAV_CANCEL if status not in ("done", "failed") else None,
                    )
                except Exception:
                    pass

            if status == "done":
                await _nav_on_done(chat_id, task_id, context)
                return

            if status == "failed":
                result = task_data.get("result", "Неизвестная ошибка")
                await _send_or_edit(
                    chat_id,
                    f"❌ <b>Исследование не удалось</b>\n\n{result}",
                    context, parse_mode="HTML", edit=False,
                    reply_markup=KB_NEW_SESSION,
                )
                NAV_SESSIONS.pop(chat_id, None)
                return

    except asyncio.CancelledError:
        logger.info(f"Navigation polling cancelled for chat {chat_id}")
    except Exception as e:
        logger.error(f"Navigation polling error: {e}")
        NAV_SESSIONS.pop(chat_id, None)


async def _nav_on_done(chat_id: int, task_id: str,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    nav = NAV_SESSIONS.get(chat_id, {})

    try:
        data = await backend_client.get_task_screenshots(task_id)
        screenshots_b64 = data.get("screenshots", [])
        count = data.get("count", 0)
    except Exception as e:
        logger.error(f"Failed to get screenshots for task {task_id}: {e}")
        await _send_or_edit(
            chat_id,
            f"✅ Исследование завершено, но не удалось получить скриншоты: {e}",
            context, edit=False,
        )
        NAV_SESSIONS.pop(chat_id, None)
        return

    if not screenshots_b64:
        await _send_or_edit(
            chat_id,
            "✅ Исследование завершено, но скриншотов нет.",
            context, edit=False, reply_markup=KB_NEW_SESSION,
        )
        NAV_SESSIONS.pop(chat_id, None)
        return

    await _send_or_edit(
        chat_id,
        f"✅ Исследование завершено!\n"
        f"Собрано {_screenshots_label(count)}. Отправляю…",
        context, edit=False,
    )

    media_group = []
    for i, b64 in enumerate(screenshots_b64[:10]):
        photo_bytes = base64.b64decode(b64)
        media_group.append(
            InputMediaPhoto(
                media=photo_bytes,
                caption=f"Шаг {i + 1}" if i == 0 else None,
            )
        )

    try:
        await context.bot.send_media_group(chat_id, media=media_group)
    except Exception as e:
        logger.error(f"Failed to send media group: {e}")
        await _send_or_edit(
            chat_id, f"Не удалось отправить скриншоты: {e}",
            context, edit=False,
        )

    if count > 10:
        for i in range(10, min(count, 20)):
            try:
                photo_bytes = base64.b64decode(screenshots_b64[i])
                await context.bot.send_photo(chat_id, photo=photo_bytes, caption=f"Шаг {i + 1}")
            except Exception:
                pass

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Проанализировать", callback_data=f"nav_evaluate:{task_id}"),
            InlineKeyboardButton("🔄 Новая оценка", callback_data="new_session"),
        ]
    ])

    await _send_or_edit(
        chat_id,
        f"🔍 Исследование завершено.\n"
        f"Собрано {_screenshots_label(count)}.\n\n"
        f"Нажми «Проанализировать» для оценки клиентского пути.",
        context, parse_mode="HTML", edit=False,
        reply_markup=kb,
    )


async def _do_nav_evaluate(chat_id: int, task_id: str,
                           context: ContextTypes.DEFAULT_TYPE) -> None:
    nav = NAV_SESSIONS.get(chat_id, {})
    model = nav.get("model", await _get_model(chat_id))
    label = await _model_label(model)

    await _send_or_edit(
        chat_id,
        f"⏳ Анализирую клиентский путь на {label}…",
        context, edit=False,
    )

    try:
        data = await backend_client.evaluate_task(task_id, model)
        result = data["result"]
    except Exception as e:
        logger.error(f"Nav evaluation failed for task {task_id}: {e}")
        await _send_or_edit(
            chat_id, f"Ошибка при анализе: {e}", context, edit=False,
        )
        return

    nav["result"] = result
    footer = await _build_footer(label)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💡 Как улучшить?", callback_data=f"nav_improve:{task_id}"),
            InlineKeyboardButton("🔄 Новая оценка", callback_data="new_session"),
        ]
    ])

    await _send_chunked(
        chat_id, result, footer, context,
        reply_markup=kb, edit_first=False,
    )


async def _do_nav_improve(chat_id: int, task_id: str,
                          context: ContextTypes.DEFAULT_TYPE) -> None:
    nav = NAV_SESSIONS.get(chat_id, {})
    model = nav.get("model", await _get_model(chat_id))
    label = await _model_label(model)

    await _send_or_edit(
        chat_id,
        f"💡 Анализирую возможные улучшения на {label}…",
        context, edit=False,
    )

    try:
        data = await backend_client.improve_task(task_id, model)
        result = data["result"]
    except Exception as e:
        logger.error(f"Nav improvement failed for task {task_id}: {e}")
        await _send_or_edit(
            chat_id, f"Ошибка при анализе улучшений: {e}", context, edit=False,
        )
        return

    footer = await _build_footer(label)
    await _send_chunked(
        chat_id, result, footer, context,
        reply_markup=KB_NEW_SESSION, edit_first=False,
    )
    NAV_SESSIONS.pop(chat_id, None)


async def _nav_cancel(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    nav = NAV_SESSIONS.pop(chat_id, None)
    if nav and "poll_task" in nav:
        nav["state"] = "cancelled"
        nav["poll_task"].cancel()

    try:
        await _edit_status(
            chat_id,
            "🔍 Исследование отменено.\n\nЧто делаем дальше?",
            context, reply_markup=KB_START,
        )
    except Exception:
        await _send_or_edit(
            chat_id,
            "🔍 Исследование отменено.\n\nЧто делаем дальше?",
            context, edit=False, reply_markup=KB_START,
        )


# --- Обработчики команд ---


async def evaluate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_evaluate(update.effective_chat.id, context)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    SESSIONS.pop(chat_id, None)
    STATUS_MESSAGES.pop(chat_id, None)
    await update.message.reply_text("Скриншоты очищены. Отправляй новые.")


async def _clear_chat(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    SESSIONS.pop(chat_id, None)
    STATUS_MESSAGES.pop(chat_id, None)
    msg = await context.bot.send_message(chat_id, "🧹 Чат очищен. Отправляй скриншоты.")
    for msg_id in range(msg.message_id - 1, 0, -1):
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except Exception:
            break


async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _clear_chat(update.effective_chat.id, context)


# --- Обработчик кнопок ---


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == "mode_evaluate":
        await _remove_buttons(query)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("← В начало", callback_data="go_home")]
        ])
        await _send_or_edit(
            chat_id,
            "📸 Отправь скриншоты клиентского пути — по одному, альбомом "
            "или несколькими сообщениями.\n"
            "Можно отправить один скрин с несколькими экранами (например, из Figma).\n\n"
            "Когда все скрины загружены, нажми «Оценить».",
            context, edit=False,
            reply_markup=kb,
        )

    elif data == "evaluate":
        await _do_evaluate(chat_id, context)

    elif data == "reset":
        SESSIONS.pop(chat_id, None)
        STATUS_MESSAGES.pop(chat_id, None)
        await query.message.reply_text("Скриншоты очищены. Отправляй новые.")

    elif data == "clear_chat":
        await _clear_chat(chat_id, context)

    elif data == "pick_model":
        await _edit_status(
            chat_id, "Выбери модель для анализа:",
            context, reply_markup=await _kb_model_picker(),
        )

    elif data.startswith("model:"):
        model_id = data.removeprefix("model:")
        USER_MODELS[chat_id] = model_id
        await _edit_status(
            chat_id, await _status_text(chat_id),
            context, reply_markup=await _kb_after_screenshot(chat_id),
        )

    elif data == "improve":
        await _remove_buttons(query)
        await _do_improve(chat_id, context)

    elif data == "new_session":
        SESSIONS.pop(chat_id, None)
        STATUS_MESSAGES.pop(chat_id, None)
        LAST_EVALUATIONS.pop(chat_id, None)
        nav = NAV_SESSIONS.pop(chat_id, None)
        if nav and "poll_task" in nav:
            nav["state"] = "cancelled"
            nav["poll_task"].cancel()
        await _remove_buttons(query)
        await context.bot.send_message(
            chat_id,
            "Выбери режим работы:",
            reply_markup=KB_START,
        )

    elif data == "go_home":
        SESSIONS.pop(chat_id, None)
        STATUS_MESSAGES.pop(chat_id, None)
        LAST_EVALUATIONS.pop(chat_id, None)
        nav = NAV_SESSIONS.pop(chat_id, None)
        if nav and "poll_task" in nav:
            nav["state"] = "cancelled"
            nav["poll_task"].cancel()
        await _remove_buttons(query)
        await context.bot.send_message(
            chat_id,
            "Выбери режим работы:",
            reply_markup=KB_START,
        )

    elif data == "back_to_status":
        await _edit_status(
            chat_id, await _status_text(chat_id),
            context, reply_markup=await _kb_after_screenshot(chat_id),
        )

    elif data == "nav_start":
        await _remove_buttons(query)
        await _nav_start(chat_id, context)

    elif data == "nav_cancel":
        await _remove_buttons(query)
        await _nav_cancel(chat_id, context)

    elif data.startswith("nav_evaluate:"):
        task_id = data.removeprefix("nav_evaluate:")
        await _remove_buttons(query)
        await _do_nav_evaluate(chat_id, task_id, context)

    elif data.startswith("nav_improve:"):
        task_id = data.removeprefix("nav_improve:")
        await _remove_buttons(query)
        await _do_nav_improve(chat_id, task_id, context)


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    nav = NAV_SESSIONS.get(chat_id)

    if nav and nav.get("state") == "awaiting_query":
        await _nav_handle_text(chat_id, update.message.text, context)
        return

    await update.message.reply_text(
        "Я принимаю только скриншоты. Отправь изображения экранов приложения или сайта."
    )


async def _on_shutdown(application) -> None:
    await backend_client.close()


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_shutdown(_on_shutdown).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("evaluate", evaluate_cmd))
    app.add_handler(CommandHandler("clear", clear_chat))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
