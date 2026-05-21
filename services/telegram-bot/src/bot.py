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

from .config import TELEGRAM_BOT_TOKEN
from .eval_agent import evaluate_screenshots

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SESSIONS: dict[int, list[bytes]] = {}

KB_AFTER_SCREENSHOT = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("✅ Оценить", callback_data="evaluate"),
        InlineKeyboardButton("🗑 Сбросить", callback_data="reset"),
    ]
])

KB_NEW_SESSION = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔄 Новая оценка", callback_data="reset")]
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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    count = await _save_screenshot(chat_id, bytes(data))

    await update.message.reply_text(
        f"📎 Скриншот #{count} сохранён",
        reply_markup=KB_AFTER_SCREENSHOT,
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Отправь изображение (скриншот экрана).")
        return

    chat_id = update.effective_chat.id
    file = await doc.get_file()
    data = await file.download_as_bytearray()
    count = await _save_screenshot(chat_id, bytes(data))

    await update.message.reply_text(
        f"📎 Скриншот #{count} сохранён",
        reply_markup=KB_AFTER_SCREENSHOT,
    )


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

    if len(result) <= 4096:
        await send_message(result, parse_mode="HTML", reply_markup=KB_NEW_SESSION)
    else:
        chunks = [result[i : i + 4096] for i in range(0, len(result), 4096)]
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            await send_message(
                chunk,
                parse_mode="HTML",
                reply_markup=KB_NEW_SESSION if is_last else None,
            )

    SESSIONS.pop(chat_id, None)


async def evaluate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _do_evaluate(chat_id, update.message.reply_text)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    SESSIONS.pop(chat_id, None)
    await update.message.reply_text("Скриншоты очищены. Отправляй новые.")


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "evaluate":
        await _do_evaluate(chat_id, query.message.reply_text)
    elif query.data == "reset":
        SESSIONS.pop(chat_id, None)
        await query.message.reply_text("Скриншоты очищены. Отправляй новые.")


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("evaluate", evaluate))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
