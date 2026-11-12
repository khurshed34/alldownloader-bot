
import os
import re
import asyncio
import tempfile
import logging
from pathlib import Path

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import yt_dlp

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN дар GitHub Secrets нест!")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MENU = ReplyKeyboardMarkup(
    [
        ["🎬 YouTube Видео"],
        ["🎵 YouTube MP3"],
        ["📱 YouTube Shorts"],
        ["ℹ️ Дастурамал"],
    ],
    resize_keyboard=True,
)

user_modes = {}

def get_video(url, folder, mode):
    output = str(Path(folder) / "%(title).80s.%(ext)s")

    options = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "socket_timeout": 30,
        "max_filesize": 49 * 1024 * 1024,
    }

    if mode == "mp3":
        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        options.update({
            "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
            "merge_output_format": "mp4",
        })

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    files = list(Path(folder).glob("*"))
    files = [f for f in files if f.is_file()]

    if not files:
        raise RuntimeError("Файл пайдо нашуд.")

    return files[0]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_modes[update.effective_user.id] = None

    await update.message.reply_text(
        "👋 Салом! Ба YouTube Turbo Bot хуш омадед.\n\n"
        "Яке аз хизматрасониҳоро интихоб кунед:",
        reply_markup=MENU,
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id
    text = message.text.strip()

    if text == "🎬 YouTube Видео":
        user_modes[user_id] = "video"
        await message.reply_text("🔗 Суроғаи видеои YouTube-ро фиристед.")
        return

    if text == "🎵 YouTube MP3":
        user_modes[user_id] = "mp3"
        await message.reply_text("🔗 Суроғаи видеоро барои MP3 фиристед.")
        return

    if text == "📱 YouTube Shorts":
        user_modes[user_id] = "shorts"
        await message.reply_text("🔗 Суроғаи YouTube Shorts-ро фиристед.")
        return

    if text == "ℹ️ Дастурамал":
        await message.reply_text(
            "1️⃣ Навъи зеркаширо интихоб кунед.\n"
            "2️⃣ Суроғаи видеоро фиристед.\n"
            "3️⃣ Бот файлро мефиристад.\n\n"
            "⚠️ Танҳо маводеро зеркашӣ кунед, ки ҳуқуқи истифода ё зеркашии онро доред.",
            reply_markup=MENU,
        )
        return

    mode = user_modes.get(user_id)

    if not mode:
        await message.reply_text(
            "Аввал аз меню навъи зеркаширо интихоб кунед.",
            reply_markup=MENU,
        )
        return

    if not re.match(
        r"^https?://(www\.)?(youtube\.com|youtu\.be)/",
        text,
        re.IGNORECASE,
    ):
        await message.reply_text("❌ Лутфан, пайванди дурусти YouTube фиристед.")
        return

    user_modes[user_id] = None

    status = await message.reply_text("⏳ Зеркашӣ оғоз шуд...")

    try:
        with tempfile.TemporaryDirectory() as folder:
            file_path = await asyncio.to_thread(
                get_video, text, folder,
                "mp3" if mode == "mp3" else "video"
            )

            await status.edit_text("📤 Файл ба Telegram фиристода мешавад...")

            with open(file_path, "rb") as file:
                if mode == "mp3":
                    await message.reply_audio(
                        audio=file,
                        title=file_path.stem[:64],
                        caption="🎵 Омода шуд!"
                    )
                elif file_path.suffix.lower() == ".mp4":
                    await message.reply_video(
                        video=file,
                        caption="🎬 Омода шуд!",
                        supports_streaming=True
                    )
                else:
                    await message.reply_document(
                        document=file,
                        caption="📁 Омода шуд!"
                    )

            await status.delete()

    except Exception as error:
        logger.exception("Download error")
        error_text = str(error)

        if "Sign in to confirm" in error_text or "not a bot" in error_text:
            reason = (
                "YouTube ин дархостро маҳдуд кард. "
                "Ин видео ҳоло аз сервер дастрас нест."
            )
        elif "maximum file size" in error_text or "File is larger" in error_text:
            reason = "Ҳаҷми видео аз ҳадди иҷозатшуда калон аст."
        else:
            reason = "Зеркашӣ иҷро нашуд. Эҳтимол видео дастрас нест ё маҳдудият дорад."

        await status.edit_text("❌ " + reason)


async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("YouTube Turbo Bot started")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
