"""
Telegram-бот CJXplorer.

Принимает скриншоты клиентского пути от пользователя,
отправляет их на оценку через бэкенд и возвращает результат.

Весь флоу (загрузка -> анализ -> результат) происходит
в одном редактируемом сообщении.
"""

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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

_MODELS_CACHE: dict | None = None
"""Кеш моделей с бэкенда."""
_MODELS_CACHE_TS: float = 0.0
"""Время последнего обновления кеша (monotonic)."""
_MODELS_CACHE_TTL: float = 300.0
"""TTL кеша моделей в секундах (5 минут)."""

_FALLBACK_MODELS: dict = {
    "models": {"openai/gpt-4o": "GPT-4o"},
    "default": "openai/gpt-4o",
}


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
    """Склонение существительного по числительному (русский язык)."""
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


async def _kb_after_screenshot(chat_id: int) -> InlineKeyboardMarkup:
    """Клавиатура после загрузки скриншота."""
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


async def _kb_model_picker() -> InlineKeyboardMarkup:
    """Клавиатура выбора LLM-модели."""
    models = await _available_models()
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"model:{model_id}")]
        for model_id, label in models.items()
    ]
    buttons.append([InlineKeyboardButton("« Назад", callback_data="back_to_status")])
    return InlineKeyboardMarkup(buttons)


async def _send_or_edit(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE,
                        reply_markup=None, parse_mode=None, edit: bool = True) -> None:
    """Отправляет или редактирует сообщение с fallback при ошибке парсинга HTML."""
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    await update.message.reply_text(
        "Привет! Я оцениваю клиентские пути по критериальной модели CX.\n\n"
        "Отправь скриншоты клиентского пути — по одному, альбомом или несколькими сообщениями.\n"
        "Можно отправить один скрин с несколькими экранами (например, из Figma).\n\n"
        "Когда все скрины загружены, нажми «Оценить»."
    )


async def _save_screenshot(chat_id: int, data: bytes) -> int:
    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = []
    SESSIONS[chat_id].append(data)
    return len(SESSIONS[chat_id])


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик входящих фото."""
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    await _save_screenshot(chat_id, bytes(data))
    await _edit_status(
        chat_id, await _status_text(chat_id),
        context, reply_markup=await _kb_after_screenshot(chat_id),
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик файлов-изображений."""
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Отправь изображение (скриншот экрана).")
        return

    chat_id = update.effective_chat.id
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    await _save_screenshot(chat_id, bytes(data))
    await _edit_status(
        chat_id, await _status_text(chat_id),
        context, reply_markup=await _kb_after_screenshot(chat_id),
    )


async def _build_footer(label: str) -> str:
    """Формирует footer с моделью и версиями сервисов."""
    core_version = await backend_client.get_backend_version()
    return (
        f"\n\n🤖 <i>Модель: {label}</i>"
        f"\n<i>core=v{core_version} · telegram=v{VERSION}</i>"
    )


async def _do_evaluate(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает оценку через бэкенд."""
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
    result_with_footer = result + footer

    if len(result_with_footer) <= 4096:
        await _edit_status(
            chat_id, result_with_footer, context,
            reply_markup=KB_AFTER_EVAL, parse_mode="HTML",
        )
    else:
        chunks = [result[i : i + 4096] for i in range(0, len(result), 4096)]
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            if is_last:
                chunk += footer
            if i == 0:
                await _edit_status(
                    chat_id, chunk, context, parse_mode="HTML",
                    reply_markup=KB_AFTER_EVAL if is_last else None,
                )
            else:
                await _send_or_edit(
                    chat_id, chunk, context, parse_mode="HTML",
                    reply_markup=KB_AFTER_EVAL if is_last else None,
                    edit=False,
                )

    SESSIONS.pop(chat_id, None)


async def _do_improve(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает анализ улучшений через бэкенд."""
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
    result_with_footer = result + footer

    if len(result_with_footer) <= 4096:
        await _send_or_edit(
            chat_id, result_with_footer, context,
            reply_markup=KB_NEW_SESSION, parse_mode="HTML", edit=False,
        )
    else:
        chunks = [result[i : i + 4096] for i in range(0, len(result), 4096)]
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            if is_last:
                chunk += footer
            await _send_or_edit(
                chat_id, chunk, context, parse_mode="HTML",
                reply_markup=KB_NEW_SESSION if is_last else None,
                edit=False,
            )

    LAST_EVALUATIONS.pop(chat_id, None)


async def evaluate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /evaluate."""
    await _do_evaluate(update.effective_chat.id, context)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /reset."""
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
    """Обработчик команды /clear."""
    await _clear_chat(update.effective_chat.id, context)


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "evaluate":
        await _do_evaluate(chat_id, context)

    elif query.data == "reset":
        SESSIONS.pop(chat_id, None)
        STATUS_MESSAGES.pop(chat_id, None)
        await query.message.reply_text("Скриншоты очищены. Отправляй новые.")

    elif query.data == "clear_chat":
        await _clear_chat(chat_id, context)

    elif query.data == "pick_model":
        await _edit_status(
            chat_id, "Выбери модель для анализа:",
            context, reply_markup=await _kb_model_picker(),
        )

    elif query.data.startswith("model:"):
        model_id = query.data.removeprefix("model:")
        USER_MODELS[chat_id] = model_id
        await _edit_status(
            chat_id, await _status_text(chat_id),
            context, reply_markup=await _kb_after_screenshot(chat_id),
        )

    elif query.data == "improve":
        await _do_improve(chat_id, context)

    elif query.data == "new_session":
        SESSIONS.pop(chat_id, None)
        STATUS_MESSAGES.pop(chat_id, None)
        LAST_EVALUATIONS.pop(chat_id, None)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(
            chat_id, "Отправляй скриншоты нового клиентского пути."
        )

    elif query.data == "back_to_status":
        await _edit_status(
            chat_id, await _status_text(chat_id),
            context, reply_markup=await _kb_after_screenshot(chat_id),
        )


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик любого текста, не являющегося командой."""
    await update.message.reply_text(
        "Я принимаю только скриншоты. Отправь изображения экранов приложения или сайта."
    )


async def _on_shutdown(application) -> None:
    """Корректно закрывает HTTP-клиент при остановке бота."""
    await backend_client.close()


def main() -> None:
    """Запускает Telegram-бота в режиме long polling."""
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
