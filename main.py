import os
import logging
import asyncio
from datetime import datetime
from collections import defaultdict
from telegram import Update, InputFile, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

log_date = datetime.now().strftime("%Y-%m-%d")
log_filename = f"log_{log_date}.txt"

file_handler = logging.FileHandler(log_filename, encoding="utf-8")
file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(file_handler)

# Отключаем лишние логи
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
CREATOR_CHAT_ID = int(os.getenv("CREATOR_CHAT_ID"))
ALLOWED_USERS = {CREATOR_CHAT_ID, 6811659941}

# Глобальные переменные для обработки медиагрупп
media_groups = defaultdict(list)
media_group_info = {}

async def process_media_group(media_group_id, context):
    await asyncio.sleep(3)  # Ждем 3 секунды для сбора всех медиа
    
    if media_group_id in media_groups and media_group_id in media_group_info:
        media_list = media_groups.pop(media_group_id)
        username, first_message = media_group_info.pop(media_group_id)
        
        if media_list:
            # Добавляем подпись к первому элементу
            if first_message.caption:
                media_class = type(media_list[0])
                media_list[0] = media_class(
                    media=media_list[0].media,
                    caption=first_message.caption
                )
            
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=f"Альбом из {len(media_list)} медиа от @{username}"
            )
            await context.bot.send_media_group(
                chat_id=CREATOR_CHAT_ID,
                media=media_list
            )
            await first_message.reply_text(
                f"Альбом из {len(media_list)} медиа получен! Скоро будет опубликован."
            )

async def forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if not message:
            return

        username = message.from_user.username or message.from_user.id

        if message.text and message.text.strip() == "/start":
            await message.reply_text("Напиши свое сообщение или отправь фото.")
            return

        # Обработка медиагрупп (альбомов)
        if hasattr(message, 'media_group_id') and message.media_group_id:
            media_group_id = message.media_group_id
            
            if message.photo:
                media = InputMediaPhoto(media=message.photo[-1].file_id)
            elif message.video:
                media = InputMediaVideo(media=message.video.file_id)
            else:
                return

            # Для первого элемента в группе сохраняем информацию
            if media_group_id not in media_groups:
                media_group_info[media_group_id] = (username, message)
            
            media_groups[media_group_id].append(media)
            
            # Перезапускаем таймер обработки группы
            if hasattr(context, '_media_group_timer'):
                context._media_group_timer.cancel()
            
            context._media_group_timer = asyncio.create_task(
                process_media_group(media_group_id, context)
            )
            return

        # Обработка одиночных медиа
        if message.photo:
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=f"Фото от: @{username}"
            )
            await context.bot.send_photo(
                chat_id=CREATOR_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=message.caption if message.caption else None
            )
            await message.reply_text("Фото получено! Скоро будет опубликовано.")
            return

        if message.video:
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=f"Видео от: @{username}"
            )
            await context.bot.send_video(
                chat_id=CREATOR_CHAT_ID,
                video=message.video.file_id,
                caption=message.caption if message.caption else None
            )
            await message.reply_text("Видео получено! Скоро будет опубликовано.")
            return

        # Обработка голосовых сообщений
        if message.voice:
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=f"Голосовое сообщение от: @{username}"
            )
            await context.bot.send_voice(
                chat_id=CREATOR_CHAT_ID,
                voice=message.voice.file_id
            )
            await message.reply_text("Голосовое сообщение получено! Скоро будет опубликовано.")
            return

        # Обработка видеосообщений (кружков)
        if message.video_note:
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=f"Видеосообщение от: @{username}"
            )
            await context.bot.send_video_note(
                chat_id=CREATOR_CHAT_ID,
                video_note=message.video_note.file_id
            )
            await message.reply_text("Видеосообщение получено! Скоро будет опубликовано.")
            return

        # Обработка текста
        if message.text:
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=f"Сообщение от: @{username}"
            )
            await context.bot.send_message(
                chat_id=CREATOR_CHAT_ID,
                text=message.text
            )
            await message.reply_text("Сообщение получено! Скоро будет опубликовано.")
            return

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
        if message:
            await message.reply_text("Произошла ошибка при обработке вашего сообщения.")

async def send_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text("Недостаточно прав для доступа к логам.")
            return

        log_date = datetime.now().strftime("%Y-%m-%d")
        log_filename = f"log_{log_date}.txt"

        if os.path.exists(log_filename):
            with open(log_filename, "rb") as log_file:
                await update.message.reply_document(document=InputFile(log_file), filename=log_filename)
        else:
            await update.message.reply_text("Файл логов за сегодня не найден.")
    except Exception as e:
        logger.error(f"Ошибка при отправке логов: {e}", exc_info=True)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("log", send_log))
    app.add_handler(MessageHandler(filters.ALL, forward))
    
    # Обработчик ошибок
    app.add_error_handler(lambda update, context: logger.error(
        f"Необработанное исключение: {context.error}", 
        exc_info=True
    ))
    
    logger.info("Бот запущен ✅ с Polling")
    app.run_polling()
