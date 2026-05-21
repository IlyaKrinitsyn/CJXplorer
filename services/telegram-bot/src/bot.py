import logging

from telegram import Update
from telegram.ext import (
    Application,
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я оцениваю клиентские пути по критериальной модели CX.\n\n"
        "Как использовать:\n"
        "1. Отправь мне скриншоты клиентского пути (можно по одному или альбомом)\n"
        "2. Когда все скрины отправлены — напиши /evaluate\n"
        "3. Я оценю весь путь целиком и дам заключение\n\n"
        "Команды:\n"
        "/start — это сообщение\n"
        "/evaluate — запустить оценку загруженных скриншотов\n"
        "/reset — очистить загруженные скриншоты и начать заново"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    SESSIONS.pop(chat_id, None)
    await update.message.reply_text("Скриншоты очищены. Можешь загружать новые.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = []

    photo = update.message.photo[-1]
    file = await photo.get_file()
    data = await file.download_as_bytearray()
    SESSIONS[chat_id].append(bytes(data))

    count = len(SESSIONS[chat_id])
    await update.message.reply_text(
        f"Скриншот #{count} сохранён. "
        "Отправь ещё или напиши /evaluate для запуска оценки."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle images sent as documents (uncompressed)."""
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        await update.message.reply_text("Отправь изображение (скриншот экрана).")
        return

    chat_id = update.effective_chat.id
    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = []

    file = await doc.get_file()
    data = await file.download_as_bytearray()
    SESSIONS[chat_id].append(bytes(data))

    count = len(SESSIONS[chat_id])
    await update.message.reply_text(
        f"Скриншот #{count} сохранён. "
        "Отправь ещё или напиши /evaluate для запуска оценки."
    )


async def evaluate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    screenshots = SESSIONS.get(chat_id, [])

    if not screenshots:
        await update.message.reply_text(
            "Нет загруженных скриншотов. Сначала отправь скрины CJ."
        )
        return

    await update.message.reply_text(
        f"Анализирую клиентский путь из {len(screenshots)} скриншотов... "
        "Это может занять 30-60 секунд."
    )

    try:
        result = await evaluate_screenshots(screenshots)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        await update.message.reply_text(
            f"Ошибка при анализе: {e}\nПопробуй ещё раз или уменьши количество скриншотов."
        )
        return

    # Telegram has a 4096 char limit per message
    if len(result) <= 4096:
        await update.message.reply_text(result)
    else:
        chunks = [result[i : i + 4096] for i in range(0, len(result), 4096)]
        for chunk in chunks:
            await update.message.reply_text(chunk)

    SESSIONS.pop(chat_id, None)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("evaluate", evaluate))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
