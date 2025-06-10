import os
import logging
import asyncio
import signal
from datetime import datetime
from collections import defaultdict
from telegram import Update, InputFile, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

# Настройка логгера
logging.basicConfig(
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
CREATOR_CHAT_ID = int(os.getenv("CREATOR_CHAT_ID"))
ALLOWED_USERS = {CREATOR_CHAT_ID, 6811659941}

# Глобальные переменные для обработки медиагрупп
media_groups = defaultdict(list)
media_group_info = {}

# Флаг для корректного завершения работы
shutdown_flag = False

async def process_media_group(media_group_id, context):
    await asyncio.sleep(3)
    if media_group_id in media_groups and media_group_id in media_group_info:
        media_list = media_groups.pop(media_group_id)
        username, first_message = media_group_info.pop(media_group_id)
        
        if media_list:
            if first_message.caption:
                media_list[0] = type(media_list[0])(
                    media=media_list[0].media,
                    caption=first_message.caption,
                )
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=f"Альбом из {len(media_list)} медиа от @{username}",
            )
            await context.bot.send_media_group(
                chat_id=CREATOR_CHAT_ID,
                media=media_list,
            )
            await first_message.reply_text(
                f"Альбом из {len(media_list)} медиа получен! Скоро будет опубликован."
            )

async def forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if shutdown_flag:
        return
    try:
        message = update.message
        if not message:
            return

        username = message.from_user.username or message.from_user.id

        if message.text and message.text.strip() == "/start":
            await message.reply_text("Напиши свое сообщение или отправь фото.")
            return

        # Обработка медиагрупп
        if hasattr(message, "media_group_id") and message.media_group_id:
            media_group_id = message.media_group_id
            if message.photo:
                media = InputMediaPhoto(media=message.photo[-1].file_id)
            elif message.video:
                media = InputMediaVideo(media=message.video.file_id)
            else:
                return

            if media_group_id not in media_groups:
                media_group_info[media_group_id] = (username, message)
            media_groups[media_group_id].append(media)

            if hasattr(context, "_media_group_timer"):
                context._media_group_timer.cancel()
            context._media_group_timer = asyncio.create_task(
                process_media_group(media_group_id, context)
            )
            return

        # Остальная логика обработки сообщений...
        # (оставьте ваш текущий код здесь)

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        if message:
            await message.reply_text("Произошла ошибка. Попробуйте позже.")

async def send_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text("Недостаточно прав.")
            return
        log_filename = f"log_{datetime.now().strftime('%Y-%m-%d')}.txt"
        if os.path.exists(log_filename):
            with open(log_filename, "rb") as log_file:
                await update.message.reply_document(
                    document=InputFile(log_file),
                    filename=log_filename,
                )
        else:
            await update.message.reply_text("Логи не найдены.")
    except Exception as e:
        logger.error(f"Ошибка отправки логов: {e}", exc_info=True)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Ошибка:", exc_info=context.error)
    if update and isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Внутренняя ошибка. Попробуйте позже.")

def handle_shutdown(signum, frame):
    global shutdown_flag
    logger.info("Получен сигнал завершения...")
    shutdown_flag = True

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("log", send_log))
    app.add_handler(MessageHandler(filters.ALL, forward))
    app.add_error_handler(error_handler)

    logger.info("Бот запущен в режиме polling 🚀")
    
    try:
        app.run_polling(
            drop_pending_updates=True,  # Игнорирует сообщения при перезапуске
            close_loop=False,          # Не закрывает event loop при остановке
            stop_signals=[],           # Мы сами обрабатываем сигналы
        )
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        logger.info("Бот остановлен.")
