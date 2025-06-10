import os
import logging
import asyncio
import signal
from datetime import datetime
from collections import defaultdict
from telegram import Update, InputFile, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from aiohttp import web

# Конфигурация логгера
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверка токена
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN or not BOT_TOKEN.startswith('bot'):
    logger.error("Неверный токен бота! Убедитесь, что BOT_TOKEN установлен и начинается с 'bot'")
    exit(1)

CREATOR_CHAT_ID = int(os.getenv("CREATOR_CHAT_ID", "0"))
ALLOWED_USERS = {CREATOR_CHAT_ID, 6811659941}

# Глобальные переменные
media_groups = defaultdict(list)
media_group_info = {}
shutdown_flag = False

async def health_check(request):
    return web.Response(text="Bot is running")

async def start_webserver():
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Веб-сервер запущен на порту 8080")
    return runner

async def process_media_group(media_group_id, context):
    await asyncio.sleep(3)
    if media_group_id in media_groups and media_group_id in media_group_info:
        media_list = media_groups.pop(media_group_id)
        username, first_message = media_group_info.pop(media_group_id)
        
        if media_list:
            if first_message.caption:
                media_list[0] = type(media_list[0])(
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
        if hasattr(message, 'media_group_id') and message.media_group_id:
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
            
            if hasattr(context, '_media_group_timer'):
                context._media_group_timer.cancel()
            
            context._media_group_timer = asyncio.create_task(
                process_media_group(media_group_id, context)
            )
            return

        # Обработка одиночных медиа
        if message.photo:
            await context.bot.send_photo(
                chat_id=CREATOR_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=f"Фото от @{username}\n\n{message.caption}" if message.caption else f"Фото от @{username}"
            )
            await message.reply_text("Фото получено! Скоро будет опубликовано.")
            return

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
                    filename=log_filename
                )
        else:
            await update.message.reply_text("Логи не найдены.")
    except Exception as e:
        logger.error(f"Ошибка отправки логов: {e}", exc_info=True)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Ошибка в обработчике:", exc_info=context.error)
    if isinstance(context.error, asyncio.CancelledError):
        return
        
    if update and isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Внутренняя ошибка. Попробуйте позже.")

def handle_shutdown(signum, frame):
    global shutdown_flag
    logger.info(f"Получен сигнал {signum}, завершаем работу...")
    shutdown_flag = True

async def main():
    # Запуск веб-сервера для Render
    runner = await start_webserver()

    # Создание бота
    application = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .post_init(lambda app: logger.info("Бот инициализирован")) \
        .post_shutdown(lambda app: logger.info("Бот завершил работу")) \
        .build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("log", send_log))
    application.add_handler(MessageHandler(filters.ALL, forward))
    application.add_error_handler(error_handler)

    logger.info("Запуск бота в режиме polling...")
    
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            drop_pending_updates=True,
            poll_interval=1.0,
            timeout=10
        )
        
        # Бесконечный цикл, пока не получим сигнал завершения
        while not shutdown_flag:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        logger.info("Работа бота была отменена")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        # Корректное завершение
        if application.updater:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await runner.cleanup()
        logger.info("Бот завершил работу")

if __name__ == "__main__":
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    asyncio.run(main())
