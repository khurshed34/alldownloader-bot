
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

from urllib.parse import urlparse, unquote
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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("TurboSave")

LANGUAGES = {
    "tg": {
        "welcome": (
            "👋 Салом! Ман TurboSave ҳастам.\n\n"
            "🔗 Пайванди видео ё суратро фирист.\n\n"
            "📥 YouTube | TikTok | Instagram | Facebook\n"
            "🎵 MP3 дастрас аст."
        ),
        "language": "🌐 Забонро интихоб кунед:",
        "quality": "🎬 Сифати зеркаширо интихоб кунед:",
        "saved": "✅ Танзимот сабт шуд!",
        "checking": "⏳ Пайванд тафтиш мешавад...",
        "sending": "📤 Файл фиристода мешавад...",
        "done": "✅ Боргирӣ анҷом ёфт!",
        "failed": "❌ Боргирӣ нашуд.",
        "invalid": "❌ Пайванди дастгиришаванда фирист.",
        "large": "❌ Андозаи файл аз 49 MB зиёд аст.",
        "settings": "⚙️ Танзимот",
        "choose": "Забон ва сифати зеркаширо интихоб кунед.",
        "help": "📌 Линкро фиристед, то бот онро тафтиш кунад.",
    },

    "ru": {
        "welcome": (
            "👋 Привет! Я TurboSave.\n\n"
            "🔗 Отправьте ссылку на видео или фото.\n\n"
            "📥 YouTube | TikTok | Instagram | Facebook\n"
            "🎵 Доступен MP3."
        ),
        "language": "🌐 Выберите язык:",
        "quality": "🎬 Выберите качество загрузки:",
        "saved": "✅ Настройки сохранены!",
        "checking": "⏳ Проверяю ссылку...",
        "sending": "📤 Отправляю файл...",
        "done": "✅ Загрузка завершена!",
        "failed": "❌ Не удалось скачать.",
        "invalid": "❌ Отправьте поддерживаемую ссылку.",
        "large": "❌ Размер файла превышает 49 MB.",
        "settings": "⚙️ Настройки",
        "choose": "Выберите язык и качество загрузки.",
        "help": "📌 Отправьте ссылку, чтобы бот её проверил.",
    },

    "en": {
        "welcome": (
            "👋 Hello! I'm TurboSave.\n\n"
            "🔗 Send a video or photo link.\n\n"
            "📥 YouTube | TikTok | Instagram | Facebook\n"
            "🎵 MP3 available."
        ),
        "language": "🌐 Choose your language:",
        "quality": "🎬 Choose download quality:",
        "saved": "✅ Settings saved!",
        "checking": "⏳ Checking link...",
        "sending": "📤 Sending file...",
        "done": "✅ Download completed!",
        "failed": "❌ Download failed.",
        "invalid": "❌ Send a supported link.",
        "large": "❌ File exceeds 49 MB.",
        "settings": "⚙️ Settings",
        "choose": "Choose language and download quality.",
        "help": "📌 Send a link for the bot to check.",
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
            InlineKeyboardButton(
                "🇹🇯 Тоҷикӣ",
                callback_data="lang:tg"
            ),
            InlineKeyboardButton(
                "🇷🇺 Русский",
                callback_data="lang:ru"
            ),
        ],
        [
            InlineKeyboardButton(
                "🇬🇧 English",
                callback_data="lang:en"
            )
        ]
    ])


def settings_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🌐 Забон",
                callback_data="menu:language"
            ),
            InlineKeyboardButton(
                "🎬 Сифат",
                callback_data="menu:quality"
            ),
        ]
    ])


def quality_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Автоматӣ",
                callback_data="quality:best"
            ),
            InlineKeyboardButton(
                "1080p",
                callback_data="quality:1080"
            ),
        ],
        [
            InlineKeyboardButton(
                "720p",
                callback_data="quality:720"
            ),
            InlineKeyboardButton(
                "480p",
                callback_data="quality:480"
            ),
        ],
        [
            InlineKeyboardButton(
                "360p",
                callback_data="quality:360"
            ),
            InlineKeyboardButton(
                "🎵 MP3",
                callback_data="quality:mp3"
            ),
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
            get_text(context, "saved")
            + "\n\n🎬 "
            + QUALITIES[quality],
            reply_markup=settings_keyboard()
        )


# =====================================
# COMMON DOWNLOAD FUNCTION
# =====================================

def download_file(url, path):

    total = 0

    with requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=40
    ) as response:

        response.raise_for_status()

        with open(path, "wb") as file:

            for chunk in response.iter_content(256 * 1024):

                if not chunk:
                    continue

                total += len(chunk)

                if total > MAX_SIZE:
                    raise ValueError(
                        "Файл аз 49 MB калон аст."
                    )

                file.write(chunk)

    return path


# =====================================
# INSTAGRAM
# =====================================

def download_instagram(url, folder):

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url
    )

    if not match:
        raise ValueError(
            "Пайванди Instagram нодуруст аст."
        )

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

    # CAROUSEL

    if post.typename == "GraphSidecar":

        for index, node in enumerate(
            post.get_sidecar_nodes(),
            start=1
        ):

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
                f"instagram_{index}{ext}"
            )

            download_file(media_url, filename)

            results.append((filename, media_type))

        return results

    # PHOTO

    if not post.is_video:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg"
        )

        download_file(post.url, filename)

        return [(filename, "photo")]

    # REELS / VIDEO

    filename = os.path.join(
        folder,
        "instagram_video.mp4"
    )

    download_file(post.video_url, filename)

    return [(filename, "video")]


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

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image'
    ]

    image_url = None

    for pattern in patterns:

        match = re.search(pattern, html, re.I)

        if match:
            image_url = unquote(match.group(1))
            break

    if not image_url:

        raise ValueError(
            "Сурати Facebook ёфт нашуд."
        )

    filename = os.path.join(
        folder,
        "facebook_photo.jpg"
    )

    download_file(image_url, filename)

    return [(filename, "photo")]


# =====================================
# YOUTUBE / TIKTOK / FACEBOOK
# =====================================

def download_other(url, folder, quality):

    height = {
        "best": 1080,
        "1080": 1080,
        "720": 720,
        "480": 480,
        "360": 360
    }.get(quality, 1080)

    output = os.path.join(
        folder,
        "%(title).60s_%(id)s.%(ext)s"
    )

    options = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "overwrites": True,
        "max_filesize": MAX_SIZE,
    }

    # MP3

    if quality == "mp3":

        options.update({
            "format": "bestaudio/best",

            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    # VIDEO

    else:

        options.update({
            "format": (
                f"bestvideo[height<={height}][ext=mp4]"
                "+bestaudio[ext=m4a]/"
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

        if ext in (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp"
        ):

            media_type = "photo"

        elif ext == ".mp3":

            media_type = "audio"

        elif ext in (
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".m4v"
        ):

            media_type = "video"

        else:
            continue

        size = os.path.getsize(path)

        if size > MAX_SIZE:

            raise ValueError(
                "Файл аз маҳдудияти 49 MB калон аст."
            )

        results.append((path, media_type))

    if not results:

        raise ValueError(
            "Файл барои фиристодан ёфт нашуд."
        )

    return results


# =====================================
# URL VALIDATION
# =====================================

def validate_url(url):

    try:

        parsed = urlparse(url)

        host = (parsed.hostname or "").lower()

        if parsed.scheme not in ("http", "https"):
            return False

        if not any(
            host == domain or host.endswith("." + domain)
            for domain in ALLOWED_DOMAINS
        ):
            return False

        return True

    except Exception:

        return False


# =====================================
# SEND FILES
# =====================================

async def send_files(update, files):

    sent = 0

    for filename, media_type in files:

        if not os.path.isfile(filename):
            continue

        size = os.path.getsize(filename)

        if size > MAX_SIZE:
            continue

        if media_type == "photo" and size <= 10 * 1024 * 1024:

            await update.message.reply_photo(
                photo=open(filename, "rb")
            )

        elif media_type == "video":

            try:

                with open(filename, "rb") as media:

                    await update.message.reply_video(
                        video=media,
                        supports_streaming=True
                    )

            except Exception:

                with open(filename, "rb") as media:

                    await update.message.reply_document(
                        document=media
                    )

        elif media_type == "audio":

            with open(filename, "rb") as media:

                await update.message.reply_audio(
                    audio=media
                )

        else:

            with open(filename, "rb") as media:

                await update.message.reply_document(
                    document=media
                )

        sent += 1

    return sent


# =====================================
# LINK HANDLER
# =====================================

async def handle_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    match = re.search(
        r"https?://\S+",
        text
    )

    if not match:

        await update.message.reply_text(
            get_text(context, "invalid")
        )

        return

    url = match.group(0).rstrip(".,!?)]}")

    if not validate_url(url):

        await update.message.reply_text(
            get_text(context, "invalid")
        )

        return

    parsed = urlparse(url)

    host = (parsed.hostname or "").lower()

    is_instagram = (
        host == "instagram.com"
        or host.endswith(".instagram.com")
    )

    is_facebook = (
        host == "facebook.com"
        or host.endswith(".facebook.com")
        or host == "fb.watch"
    )

    quality = context.user_data.get(
        "quality",
        "best"
    )

    msg = await update.message.reply_text(
        get_text(context, "checking")
    )

    folder = tempfile.mkdtemp(
        prefix="turbosave_"
    )

    try:

        # DOWNLOAD

        if is_instagram:

            files = await asyncio.to_thread(
                download_instagram,
                url,
                folder
            )

        elif is_facebook and (
            "/photo" in parsed.path
            or "/photos" in parsed.path
        ):

            files = await asyncio.to_thread(
                download_facebook_photo,
                url,
                folder
            )

        else:

            files = await asyncio.to_thread(
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

        sent = await send_files(
            update,
            files
        )

        if sent == 0:

            await msg.edit_text(
                get_text(context, "failed")
            )

        else:

            await msg.edit_text(
                get_text(context, "done")
                + f"\n\n📦 Файлҳо: {sent}"
            )

    except Exception as error:

        logger.exception(
            "Download failed"
        )

        error_text = str(error)

        if (
            "max-filesize" in error_text.lower()
            or "file is larger" in error_text.lower()
            or "too large" in error_text.lower()
        ):

            message = get_text(context, "large")

        else:

            message = (
                get_text(context, "failed")
                + "\n\n"
                + error_text[:350]
            )

        await msg.edit_text(message)

    finally:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )


# =====================================
# ERROR HANDLER
# =====================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Telegram error: %s",
        context.error,
        exc_info=context.error
    )


# =====================================
# MAIN
# =====================================

def main():

    if not TOKEN:

        raise RuntimeError(
            "BOT_TOKEN дар GitHub Secrets нест!"
        )

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("settings", settings)
    )

    app.add_handler(
        CallbackQueryHandler(buttons)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_link
        )
    )

    app.add_error_handler(error_handler)

    logger.info("TurboSave started successfully!")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":

    main()
