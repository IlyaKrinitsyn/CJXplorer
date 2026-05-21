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

from .config import OPENAI_MODEL, TELEGRAM_BOT_TOKEN
from .eval_agent import evaluate_screenshots

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SESSIONS: dict[int, list[bytes]] = {}
STATUS_MESSAGES: dict[int, int] = {}

KB_AFTER_SCREENSHOT = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Оценить", callback_data="evaluate"),
        InlineKeyboardButton("🗑 Сбросить", callback_data="reset"),
    ]
])

KB_NEW_SESSION = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🔄 Новая оценка", callback_data="reset"),
        InlineKeyboardButton("🧹 Очистить чат", callback_data="clear_chat"),
    ]
])


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


async def _update_status(chat_id: int, count: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = f"📎 Загружено скриншотов: {count}"
    if chat_id in STATUS_MESSAGES:
        try:
            await context.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=STATUS_MESSAGES[chat_id],
                reply_markup=KB_AFTER_SCREENSHOT,
            )
            return
        except Exception:
            pass
    msg = await context.bot.send_message(
        chat_id, text, reply_markup=KB_AFTER_SCREENSHOT
    )
    STATUS_MESSAGES[chat_id] = msg.message_id


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    count = await _save_screenshot(chat_id, bytes(data))
    await _update_status(chat_id, count, context)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Отправь изображение (скриншот экрана).")
        return

    chat_id = update.effective_chat.id
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    count = await _save_screenshot(chat_id, bytes(data))
    await _update_status(chat_id, count, context)


async def _do_evaluate(chat_id: int, send_message) -> None:
    screenshots = SESSIONS.get(chat_id, [])

    if not screenshots:
        await send_message("Нет загруженных скриншотов. Сначала отправь скрины CJ.")
        return

    await send_message(
        f"⏳ Анализирую клиентский путь из {len(screenshots)} скриншотов…"
    )

    try:
        result = await evaluate_screenshots(screenshots)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        await send_message(f"Ошибка при анализе: {e}")
        return

    footer = f"\n\n🤖 <i>Модель: {OPENAI_MODEL}</i>"
    result_with_footer = result + footer

    if len(result_with_footer) <= 4096:
        await send_message(result_with_footer, parse_mode="HTML", reply_markup=KB_NEW_SESSION)
    else:
        chunks = [result[i : i + 4096] for i in range(0, len(result), 4096)]
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            if is_last:
                chunk += footer
                if len(chunk) > 4096:
                    await send_message(chunk[:4096], parse_mode="HTML")
                    await send_message(chunk[4096:], parse_mode="HTML", reply_markup=KB_NEW_SESSION)
                    continue
            await send_message(
                chunk,
                parse_mode="HTML",
                reply_markup=KB_NEW_SESSION if is_last else None,
            )

    SESSIONS.pop(chat_id, None)
    STATUS_MESSAGES.pop(chat_id, None)


async def evaluate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _do_evaluate(chat_id, update.message.reply_text)


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
        await _do_evaluate(chat_id, query.message.reply_text)
    elif query.data == "reset":
        SESSIONS.pop(chat_id, None)
        STATUS_MESSAGES.pop(chat_id, None)
        await query.message.reply_text("Скриншоты очищены. Отправляй новые.")
    elif query.data == "clear_chat":
        await _clear_chat(chat_id, context)


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
