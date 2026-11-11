
import os
import asyncio
import logging
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Салом!\n\n"
        "Ба ман ссылкаи видео фирист:\n"
        "▶️ YouTube\n"
        "📸 Instagram\n"
        "🎵 TikTok\n"
        "📘 Facebook\n\n"
        "Ман кӯшиш мекунам видеоро зеркашӣ кунам."
    )

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text.strip()

    if not url.startswith(("https://", "http://")):
        await update.message.reply_text("❌ Ссылка нодуруст аст!")
        return

    msg = await update.message.reply_text(
        "⏳ Видео зеркашӣ шуда истодааст..."
    )

    filename = f"video_{update.effective_user.id}.mp4"

    try:
        options = {
            "format": "best[ext=mp4]/best",
            "outtmpl": filename,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 3,
        }

        await asyncio.to_thread(
            lambda: yt_dlp.YoutubeDL(options).download([url])
        )

        if not os.path.exists(filename):
            raise Exception("Файли видео сохта нашуд.")

        size = os.path.getsize(filename)

        if size > 49 * 1024 * 1024:
            raise Exception("Видео аз ҳад калон аст (зиёда аз 49 MB).")

        with open(filename, "rb") as video:
            await update.message.reply_video(
                video=video,
                caption="✅ Видео тайёр!"
            )

        await msg.delete()

    except Exception as e:
        logging.exception("Download failed")
        error = str(e)[:700]

        await msg.edit_text(
            f"❌ ХАТО ҲАНГОМИ ЗЕРКАШӢ:\n\n{error}"
        )

    finally:
        if os.path.exists(filename):
            os.remove(filename)


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN дар GitHub Secrets нест!")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            download
        )
    )

    print("🤖 BOT STARTED!")

    app.run_polling()


if __name__ == "__main__":
    main()
