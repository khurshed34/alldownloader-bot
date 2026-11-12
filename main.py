
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


def validate_url(url):
    pattern = r"^https?://(www\.)?(youtube\.com|youtu\.be)/"
    return bool(re.match(pattern, url, re.IGNORECASE))


def get_video_info(url):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 25,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def download_video(url, folder, mode):
    output = str(Path(folder) / "%(title).70s.%(ext)s")

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

    files = [
        f for f in Path(folder).iterdir()
        if f.is_file() and not f.name.endswith(".part")
    ]

    if not files:
        raise RuntimeError("Файл пайдо нашуд.")

    return max(files, key=lambda f: f.stat().st_size)


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

    choices = {
        "🎬 YouTube Видео": "video",
        "🎵 YouTube MP3": "mp3",
        "📱 YouTube Shorts": "shorts",
    }

    if text in choices:
        user_modes[user_id] = choices[text]
        await message.reply_text(
            "🔗 Акнун пайванди YouTube-ро фиристед."
        )
        return

    if text == "ℹ️ Дастурамал":
        await message.reply_text(
            "1️⃣ Навъи зеркаширо интихоб кунед.\n"
            "2️⃣ Пайванди видеоро фиристед.\n"
            "3️⃣ Бот маълумотро месанҷад ва файлро мефиристад.\n\n"
            "⚠️ Танҳо маводеро истифода баред, ки ҳуқуқи зеркашии онро доред.",
            reply_markup=MENU,
        )
        return

    mode = user_modes.get(user_id)

    if not mode:
        await message.reply_text(
            "Аввал аз меню хизматрасониро интихоб кунед.",
            reply_markup=MENU,
        )
        return

    if not validate_url(text):
        await message.reply_text(
            "❌ Пайванди YouTube нодуруст аст."
        )
        return

    user_modes[user_id] = None
    status = await message.reply_text(
        "🔎 Маълумоти видеоро месанҷам..."
    )

    try:
        info = await asyncio.to_thread(get_video_info, text)

        title = info.get("title", "Бе ном")
        duration = info.get("duration")

        if duration:
            duration_text = f"{duration // 60}:{duration % 60:02d}"
        else:
            duration_text = "Номаълум"

        await status.edit_text(
            f"✅ Видео ёфт шуд!\n\n"
            f"🎬 Ном: {title[:200]}\n"
            f"⏱ Давомнокӣ: {duration_text}\n\n"
            f"⏳ Зеркашӣ оғоз шуд..."
        )

        with tempfile.TemporaryDirectory() as folder:
            file_path = await asyncio.to_thread(
                download_video,
                text,
                folder,
                "mp3" if mode == "mp3" else "video",
            )

            await status.edit_text("📤 Файл фиристода мешавад...")

            with open(file_path, "rb") as file:
                if mode == "mp3":
                    await message.reply_audio(
                        audio=file,
                        title=title[:64],
                        caption="🎵 Омода шуд!"
                    )
                elif file_path.suffix.lower() == ".mp4":
                    await message.reply_video(
                        video=file,
                        caption="🎬 Омода шуд!",
                        supports_streaming=True,
                    )
                else:
                    await message.reply_document(
                        document=file,
                        caption="📁 Омода шуд!"
                    )

        await status.delete()

    except Exception as error:
        logger.exception("YouTube error")

        error_text = str(error).lower()

        if "sign in to confirm" in error_text or "not a bot" in error_text:
            reason = (
                "YouTube аз сервер тасдиқи воридшавиро талаб мекунад. "
                "Ин видео аз ин сервер дастрас нест."
            )
        elif "ffmpeg" in error_text:
            reason = "FFmpeg дастрас нест. Насби онро дар GitHub Actions санҷед."
        elif "private video" in error_text:
            reason = "Ин видео хусусӣ аст."
        elif "video unavailable" in error_text:
            reason = "Видео дастрас нест."
        elif "maximum file size" in error_text:
            reason = "Ҳаҷми файл аз ҳадди иҷозатшуда калон аст."
        else:
            reason = f"Хатои зеркашӣ: {str(error)[:700]}"

        await status.edit_text("❌ " + reason)


async def main():
    logger.info("yt-dlp version: %s", yt_dlp.version.__version__)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

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
