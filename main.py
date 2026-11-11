
import os
import asyncio
import yt_dlp

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Салом!\n"
        "Ссылкаи видео аз YouTube, Instagram ё TikTok фирист."
    )

async def get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith(("https://", "http://")):
        await update.message.reply_text("❌ Ссылка нодуруст аст!")
        return

    msg = await update.message.reply_text("⏳ Видео гирифта мешавад...")

    filename = f"video_{update.effective_user.id}.mp4"

    try:
        options = {
            "format": "best[ext=mp4]/best",
            "outtmpl": filename,
            "noplaylist": True,
            "max_filesize": 49 * 1024 * 1024,
            "quiet": True
        }

        await asyncio.to_thread(
            lambda: yt_dlp.YoutubeDL(options).download([url])
        )

        with open(filename, "rb") as video:
            await update.message.reply_video(
                video=video,
                caption="✅ Видео тайёр!"
            )

        await msg.delete()

    except Exception:
        await msg.edit_text(
            "❌ Видео зеркашӣ нашуд. Ссылкаро санҷ!"
        )

    finally:
        if os.path.exists(filename):
            os.remove(filename)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_video)
    )

    print("BOT STARTED!")
    app.run_polling()

if __name__ == "__main__":
    main()
