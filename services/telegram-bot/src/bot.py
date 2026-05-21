import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import AVAILABLE_MODELS, DEFAULT_MODEL, TELEGRAM_BOT_TOKEN
from .eval_agent import evaluate_screenshots

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SESSIONS: dict[int, list[bytes]] = {}
STATUS_MESSAGES: dict[int, int] = {}
USER_MODELS: dict[int, str] = {}


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


def _get_model(chat_id: int) -> str:
    return USER_MODELS.get(chat_id, DEFAULT_MODEL)


def _model_label(model_id: str) -> str:
    return AVAILABLE_MODELS.get(model_id, model_id)


def _kb_after_screenshot(chat_id: int) -> InlineKeyboardMarkup:
    model = _get_model(chat_id)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Оценить", callback_data="evaluate"),
            InlineKeyboardButton("🗑 Сбросить", callback_data="reset"),
        ],
        [
            InlineKeyboardButton(
                f"🔀 Модель: {_model_label(model)}", callback_data="pick_model"
            ),
        ],
    ])


KB_NEW_SESSION = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🔄 Новая оценка", callback_data="reset"),
        InlineKeyboardButton("🧹 Очистить чат", callback_data="clear_chat"),
    ]
])


def _kb_model_picker() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"model:{model_id}")]
        for model_id, label in AVAILABLE_MODELS.items()
    ]
    buttons.append([InlineKeyboardButton("« Назад", callback_data="back_to_status")])
    return InlineKeyboardMarkup(buttons)


async def _send_or_edit(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE,
                       reply_markup=None, parse_mode=None, edit: bool = True) -> None:
    """Try to edit status message; on any failure (including bad HTML) retry without parse_mode."""
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


def _status_text(chat_id: int) -> str:
    count = len(SESSIONS.get(chat_id, []))
    model = _model_label(_get_model(chat_id))
    return f"📎 Загружено: {_screenshots_label(count)}\n🤖 Модель: {model}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я оцениваю клиентские пути по критериальной модели CX.\n\n"
        "Отправь скриншоты клиентского пути — по одному или альбомом.\n"
        "Когда все скрины загружены, нажми «Оценить»."
    )


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
    await _edit_status(
        chat_id, _status_text(chat_id),
        context, reply_markup=_kb_after_screenshot(chat_id),
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Отправь изображение (скриншот экрана).")
        return

    chat_id = update.effective_chat.id
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    await _save_screenshot(chat_id, bytes(data))
    await _edit_status(
        chat_id, _status_text(chat_id),
        context, reply_markup=_kb_after_screenshot(chat_id),
    )


async def _do_evaluate(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    screenshots = SESSIONS.get(chat_id, [])

    if not screenshots:
        await _edit_status(
            chat_id, "Нет загруженных скриншотов. Сначала отправь скрины CJ.", context
        )
        return

    model = _get_model(chat_id)
    label = _model_label(model)

    await _edit_status(
        chat_id,
        f"⏳ Анализирую {_screenshots_label(len(screenshots))} на {label}…",
        context,
    )

    try:
        result = await evaluate_screenshots(screenshots, model)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        await _edit_status(chat_id, f"Ошибка при анализе: {e}", context)
        return

    footer = f"\n\n🤖 <i>Модель: {label}</i>"
    result_with_footer = result + footer

    if len(result_with_footer) <= 4096:
        await _edit_status(
            chat_id, result_with_footer, context,
            reply_markup=KB_NEW_SESSION, parse_mode="HTML",
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
                    reply_markup=KB_NEW_SESSION if is_last else None,
                )
            else:
                await _send_or_edit(
                    chat_id, chunk, context, parse_mode="HTML",
                    reply_markup=KB_NEW_SESSION if is_last else None,
                    edit=False,
                )

    SESSIONS.pop(chat_id, None)


async def evaluate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            context, reply_markup=_kb_model_picker(),
        )

    elif query.data.startswith("model:"):
        model_id = query.data.removeprefix("model:")
        USER_MODELS[chat_id] = model_id
        await _edit_status(
            chat_id, _status_text(chat_id),
            context, reply_markup=_kb_after_screenshot(chat_id),
        )

    elif query.data == "back_to_status":
        await _edit_status(
            chat_id, _status_text(chat_id),
            context, reply_markup=_kb_after_screenshot(chat_id),
        )


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("evaluate", evaluate))
    app.add_handler(CommandHandler("clear", clear_chat))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
