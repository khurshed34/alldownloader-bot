
import os
import re
import json
import shutil
import logging
import asyncio
import tempfile
import requests

import instaloader
import yt_dlp

from urllib.parse import urlparse
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =====================================
# SETTINGS
# =====================================

TOKEN = os.getenv("BOT_TOKEN")

MAX_SIZE = 49 * 1024 * 1024

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

LANGUAGES = {
    "tg": {
        "welcome": "👋 Салом! Ман TurboSave ҳастам.\n\n🔗 Пайванди видео ё суратро фирист.",
        "language": "🌐 Забонро интихоб кунед:",
        "quality": "🎬 Сифати зеркаширо интихоб кунед:",
        "saved": "✅ Танзимот сабт шуд!",
        "checking": "⏳ Пайванд тафтиш мешавад...",
        "sending": "📤 Файл фиристода мешавад...",
        "done": "✅ Боргирӣ анҷом ёфт!",
        "failed": "❌ Боргирӣ нашуд.",
        "invalid": "❌ Пайванди дастгиришаванда фирист.",
        "large": "❌ Андозаи файл аз ҳад зиёд аст.",
        "settings": "⚙️ Танзимот",
        "choose": "Забон ва сифатро интихоб кунед."
    },
    "ru": {
        "welcome": "👋 Привет! Я TurboSave.\n\n🔗 Отправьте ссылку на видео или фото.",
        "language": "🌐 Выберите язык:",
        "quality": "🎬 Выберите качество загрузки:",
        "saved": "✅ Настройки сохранены!",
        "checking": "⏳ Проверяю ссылку...",
        "sending": "📤 Отправляю файл...",
        "done": "✅ Загрузка завершена!",
        "failed": "❌ Не удалось скачать.",
        "invalid": "❌ Отправьте поддерживаемую ссылку.",
        "large": "❌ Файл слишком большой.",
        "settings": "⚙️ Настройки",
        "choose": "Выберите язык и качество."
    },
    "en": {
        "welcome": "👋 Hello! I'm TurboSave.\n\n🔗 Send a video or photo link.",
        "language": "🌐 Choose your language:",
        "quality": "🎬 Choose download quality:",
        "saved": "✅ Settings saved!",
        "checking": "⏳ Checking link...",
        "sending": "📤 Sending file...",
        "done": "✅ Download completed!",
        "failed": "❌ Download failed.",
        "invalid": "❌ Send a supported link.",
        "large": "❌ File is too large.",
        "settings": "⚙️ Settings",
        "choose": "Choose language and quality."
    }
}

QUALITIES = {
    "best": "Auto / Best",
    "1080": "1080p",
    "720": "720p",
    "480": "480p",
    "360": "360p",
    "mp3": "MP3"
}

ALLOWED_DOMAINS = (
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "fb.watch",
    "youtube.com",
    "youtu.be"
)


# =====================================
# KEYBOARDS
# =====================================

def language_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang:tg"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
        ],
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en")
        ]
    ])


def settings_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 Забон", callback_data="menu:language"),
            InlineKeyboardButton("🎬 Сифат", callback_data="menu:quality"),
        ]
    ])


def quality_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Автоматӣ", callback_data="quality:best"),
            InlineKeyboardButton("1080p", callback_data="quality:1080"),
        ],
        [
            InlineKeyboardButton("720p", callback_data="quality:720"),
            InlineKeyboardButton("480p", callback_data="quality:480"),
        ],
        [
            InlineKeyboardButton("360p", callback_data="quality:360"),
            InlineKeyboardButton("🎵 MP3", callback_data="quality:mp3"),
        ]
    ])


def get_language(context):
    return context.user_data.get("language", "tg")


def get_text(context, key):
    lang = get_language(context)
    return LANGUAGES[lang][key]


# =====================================
# START
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🌐 Забони худро интихоб кунед:",
        reply_markup=language_keyboard()
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        get_text(context, "choose"),
        reply_markup=settings_keyboard()
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("lang:"):

        lang = data.split(":")[1]

        if lang not in LANGUAGES:
            return

        context.user_data["language"] = lang

        await query.edit_message_text(
            LANGUAGES[lang]["welcome"],
            reply_markup=settings_keyboard()
        )

    elif data == "menu:language":

        await query.edit_message_text(
            get_text(context, "language"),
            reply_markup=language_keyboard()
        )

    elif data == "menu:quality":

        await query.edit_message_text(
            get_text(context, "quality"),
            reply_markup=quality_keyboard()
        )

    elif data.startswith("quality:"):

        quality = data.split(":")[1]

        if quality not in QUALITIES:
            return

        context.user_data["quality"] = quality

        await query.edit_message_text(
            get_text(context, "saved") +
            "\n\n🎬 " + QUALITIES[quality]
        )


# =====================================
# INSTAGRAM - ORIGINAL FUNCTION
# =====================================

def download_file(url, path):

    response = requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=40
    )

    response.raise_for_status()

    total = 0

    with open(path, "wb") as f:

        for chunk in response.iter_content(1024 * 256):

            if not chunk:
                continue

            total += len(chunk)

            if total > MAX_SIZE:
                raise ValueError("Андозаи файл аз ҳад зиёд аст.")

            f.write(chunk)

    return path


def download_instagram(url, folder):

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url
    )

    if not match:
        raise ValueError("Пайванди Instagram нодуруст аст.")

    shortcode = match.group(1)

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
        quiet=True
    )

    post = instaloader.Post.from_shortcode(
        loader.context,
        shortcode
    )

    results = []

    # Карусел
    if post.typename == "GraphSidecar":

        nodes = post.get_sidecar_nodes()

        for index, node in enumerate(nodes, start=1):

            if node.is_video:
                media_url = node.video_url
                ext = ".mp4"
                media_type = "video"
            else:
                media_url = node.display_url
                ext = ".jpg"
                media_type = "photo"

            filename = os.path.join(
                folder,
                f"media_{index}{ext}"
            )

            download_file(media_url, filename)

            results.append((filename, media_type))

        return results

    # Як сурат
    if not post.is_video:

        filename = os.path.join(folder, "photo.jpg")

        download_file(post.url, filename)

        results.append((filename, "photo"))

        return results

    # Reels ё видео
    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_SIZE,
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    for filename in os.listdir(folder):

        path = os.path.join(folder, filename)

        if os.path.isfile(path):
            results.append((path, "video"))

    return results


# =====================================
# FACEBOOK PHOTO
# =====================================

def download_facebook_photo(url, folder):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    html = response.text

    match = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        html,
        re.I
    )

    if not match:
        match = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
            html,
            re.I
        )

    if not match:
        raise ValueError("Сурати дастрас ёфт нашуд.")

    image_url = match.group(1)

    filename = os.path.join(folder, "facebook_photo.jpg")

    download_file(image_url, filename)

    return [(filename, "photo")]


# =====================================
# TIKTOK / FACEBOOK / YOUTUBE
# =====================================

def download_other(url, folder, quality):

    output = os.path.join(folder, "%(title).80s_%(id)s.%(ext)s")

    options = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_SIZE,
        "restrictfilenames": True,
    }

    if quality == "mp3":

        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    else:

        height = {
            "best": 9999,
            "1080": 1080,
            "720": 720,
            "480": 480,
            "360": 360
        }.get(quality, 9999)

        options.update({
            "format": (
                f"best[height<={height}][ext=mp4]/"
                f"best[height<={height}]/best"
            ),
            "merge_output_format": "mp4",
        })

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    results = []

    for filename in os.listdir(folder):

        path = os.path.join(folder, filename)

        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(filename)[1].lower()

        if ext in (".jpg", ".jpeg", ".png", ".webp"):
            media_type = "photo"
        elif ext == ".mp3":
            media_type = "audio"
        else:
            media_type = "video"

        results.append((path, media_type))

    return results


# =====================================
# LINK HANDLER
# =====================================

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    parsed = urlparse(url)

    host = (parsed.hostname or "").lower()

    if not parsed.scheme in ("http", "https") or not any(
        host == domain or host.endswith("." + domain)
        for domain in ALLOWED_DOMAINS
    ):

        await update.message.reply_text(
            get_text(context, "invalid")
        )

        return

    is_instagram = (
        host == "instagram.com" or host.endswith(".instagram.com")
    )

    is_facebook = (
        host == "facebook.com" or
        host.endswith(".facebook.com") or
        host == "fb.watch"
    )

    quality = context.user_data.get("quality", "best")

    msg = await update.message.reply_text(
        get_text(context, "checking")
    )

    folder = tempfile.mkdtemp(prefix="turbosave_")

    try:

        loop = asyncio.get_running_loop()

        if is_instagram:

            # Instagram: сифати пешина нигоҳ дошта мешавад
            files = await loop.run_in_executor(
                None,
                download_instagram,
                url,
                folder
            )

        else:

            # Facebook photo post
            if is_facebook and (
                "/photo" in parsed.path or
                "/photos" in parsed.path
            ):

                files = await loop.run_in_executor(
                    None,
                    download_facebook_photo,
                    url,
                    folder
                )

            else:

                files = await loop.run_in_executor(
                    None,
                    download_other,
                    url,
                    folder,
                    quality
                )

        if not files:

            await msg.edit_text(
                get_text(context, "failed")
            )

            return

        await msg.edit_text(
            get_text(context, "sending")
        )

        sent = 0

        for filename, media_type in files:

            if not os.path.isfile(filename):
                continue

            size = os.path.getsize(filename)

            if size > MAX_SIZE:
                continue

            with open(filename, "rb") as media:

                if media_type == "photo" and size <= 10 * 1024 * 1024:

                    await update.message.reply_photo(
                        photo=media
                    )

                elif media_type == "video":

                    await update.message.reply_video(
                        video=media,
                        supports_streaming=True
                    )

                elif media_type == "audio":

                    await update.message.reply_audio(
                        audio=media
                    )

                else:

                    await update.message.reply_document(
                        document=media
                    )

            sent += 1

        if sent == 0:
            await msg.edit_text(
                get_text(context, "failed")
            )
        else:
            await msg.edit_text(
                get_text(context, "done") +
                f"\n\n📦 Файлҳо: {sent}"
            )

    except Exception as error:

        logger.exception("Download failed")

        await msg.edit_text(
            get_text(context, "failed") +
            "\n\n" + str(error)[:500]
        )

    finally:

        shutil.rmtree(folder, ignore_errors=True)


# =====================================
# MAIN
# =====================================

async def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN дар GitHub Secrets нест!"
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings))

    app.add_handler(
        CallbackQueryHandler(buttons)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_link
        )
    )

    logger.info("TurboSave started")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
