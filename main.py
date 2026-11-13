
import os
import re
import glob
import asyncio
import logging
import tempfile
import shutil
import requests
import yt_dlp
import instaloader

from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

if not TOKEN:
    raise RuntimeError("BOT_TOKEN ёфт нашуд.")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# =====================================
# LANGUAGES
# =====================================

TEXTS = {
    "tj": {
        "welcome": "👋 Ба TurboSave Bot хуш омадед!\n\nЗабонро интихоб кунед:",
        "send_link": "🔗 Акнун пайванди видео ё аксро фиристед.",
        "quality": "🎬 Сифати видеоро интихоб кунед:",
        "downloading": "⏳ Боргирӣ оғоз шуд...",
        "sending": "📤 Файл фиристода мешавад...",
        "done": "✅ Кор анҷом ёфт!",
        "failed": "❌ Боргирӣ иҷро нашуд:\n{}",
        "invalid": "❌ Лутфан пайванди дурустро фиристед.",
        "large": "❌ Ҳаҷми файл аз 49 MB зиёд аст.",
        "unsupported": "❌ Ин платформа дастгирӣ намешавад.",
        "sent": "📤 Файлҳои фиристодашуда: {}",
        "original": "⭐ Сифати беҳтарин",
    },
    "ru": {
        "welcome": "👋 Добро пожаловать в TurboSave Bot!\n\nВыберите язык:",
        "send_link": "🔗 Теперь отправьте ссылку на видео или фото.",
        "quality": "🎬 Выберите качество видео:",
        "downloading": "⏳ Начинается загрузка...",
        "sending": "📤 Отправка файла...",
        "done": "✅ Готово!",
        "failed": "❌ Ошибка загрузки:\n{}",
        "invalid": "❌ Отправьте правильную ссылку.",
        "large": "❌ Размер файла превышает 49 MB.",
        "unsupported": "❌ Эта платформа не поддерживается.",
        "sent": "📤 Отправлено файлов: {}",
        "original": "⭐ Лучшее качество",
    },
    "en": {
        "welcome": "👋 Welcome to TurboSave Bot!\n\nChoose your language:",
        "send_link": "🔗 Now send a video or photo link.",
        "quality": "🎬 Choose video quality:",
        "downloading": "⏳ Downloading started...",
        "sending": "📤 Sending file...",
        "done": "✅ Completed!",
        "failed": "❌ Download failed:\n{}",
        "invalid": "❌ Please send a valid link.",
        "large": "❌ File size exceeds 49 MB.",
        "unsupported": "❌ This platform is not supported.",
        "sent": "📤 Files sent: {}",
        "original": "⭐ Best quality",
    },
}

# =====================================
# COMMON HEADERS
# =====================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# =====================================
# DOWNLOAD DIRECT FILE
# =====================================

def download_file(url, filename):

    response = requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=90
    )

    response.raise_for_status()

    with open(filename, "wb") as file:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                file.write(chunk)

    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        raise ValueError("Файл холӣ аст.")

# =====================================
# FIND DOWNLOADED FILE
# =====================================

def find_downloaded_file(folder, prefix):

    files = glob.glob(os.path.join(folder, prefix + "*"))

    files = [
        f for f in files
        if os.path.isfile(f)
        and not f.endswith((".part", ".ytdl", ".json"))
    ]

    if not files:
        raise ValueError("Файл ёфт нашуд.")

    return max(files, key=os.path.getsize)

# =====================================
# YT-DLP DOWNLOADER
# =====================================

def download_with_ytdlp(url, folder, prefix, quality="best"):

    os.makedirs(folder, exist_ok=True)

    output = os.path.join(
        folder,
        prefix + "_%(id)s.%(ext)s"
    )

    if quality == "best":
        format_code = "bestvideo*+bestaudio/best"
    else:
        format_code = (
            f"bestvideo[height<={quality}]+bestaudio/"
            f"best[height<={quality}]/best"
        )

    options = {
        "format": format_code,
        "outtmpl": output,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 40,
        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)

    filename = find_downloaded_file(folder, prefix)

    return [(filename, "video")]

# =====================================
# INSTAGRAM DOWNLOADER
# =====================================

def download_instagram(url, folder):

    os.makedirs(folder, exist_ok=True)

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url,
        re.IGNORECASE
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

    if not post.is_video:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg"
        )

        download_file(post.url, filename)

        return [(filename, "photo")]

    filename = os.path.join(
        folder,
        "instagram_video.mp4"
    )

    download_file(post.video_url, filename)

    return [(filename, "video")]

# =====================================
# YOUTUBE DOWNLOADER
# =====================================

def download_youtube(url, folder, quality):

    if not re.search(r"(youtube\.com|youtu\.be)", url, re.I):
        raise ValueError("Пайванди YouTube нодуруст аст.")

    return download_with_ytdlp(
        url, folder, "youtube", quality
    )

# =====================================
# TIKTOK DOWNLOADER
# =====================================

def download_tiktok(url, folder, quality):

    if not re.search(r"tiktok\.com", url, re.I):
        raise ValueError("Пайванди TikTok нодуруст аст.")

    return download_with_ytdlp(
        url, folder, "tiktok", quality
    )

# =====================================
# FACEBOOK HTML PARSER
# =====================================

class FacebookParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):

        if tag.lower() != "meta":
            return

        data = dict(attrs)

        key = data.get("property") or data.get("name")
        value = data.get("content")

        if key and value:
            self.meta[key.lower()] = value

# =====================================
# FACEBOOK PHOTO DOWNLOADER
# =====================================

def download_facebook_photo(url, folder):

    session = requests.Session()
    session.headers.update(HEADERS)

    response = session.get(
        url,
        allow_redirects=True,
        timeout=60
    )

    response.raise_for_status()

    parser = FacebookParser()
    parser.feed(response.text)

    image_url = (
        parser.meta.get("og:image")
        or parser.meta.get("og:image:secure_url")
        or parser.meta.get("twitter:image")
    )

    if not image_url:
        raise ValueError("Акси оммавӣ ёфт нашуд.")

    image_url = urljoin(response.url, image_url)

    image_response = session.get(
        image_url,
        stream=True,
        timeout=90,
        headers={"Referer": response.url}
    )

    image_response.raise_for_status()

    content_type = image_response.headers.get(
        "Content-Type", ""
    ).lower()

    if not content_type.startswith("image/"):
        raise ValueError("Файли акс дастрас нест.")

    extension = ".jpg"

    if "png" in content_type:
        extension = ".png"
    elif "webp" in content_type:
        extension = ".webp"

    filename = os.path.join(
        folder,
        "facebook_photo" + extension
    )

    with open(filename, "wb") as file:
        for chunk in image_response.iter_content(1024 * 1024):
            if chunk:
                file.write(chunk)

    return [(filename, "photo")]

# =====================================
# FACEBOOK DOWNLOADER
# =====================================

def download_facebook(url, folder, quality):

    if not re.search(
        r"(facebook\.com|fb\.watch|fb\.com)",
        url,
        re.I
    ):
        raise ValueError("Пайванди Facebook нодуруст аст.")

    try:
        return download_with_ytdlp(
            url, folder, "facebook", quality
        )

    except Exception as video_error:

        logger.warning(
            "Facebook video failed: %s",
            video_error
        )

        try:
            return download_facebook_photo(url, folder)

        except Exception as photo_error:
            raise ValueError(
                "Facebook зеркашӣ нашуд.\n"
                "Видео: " + str(video_error)[:250]
                + "\nАкс: " + str(photo_error)[:250]
            )

# =====================================
# AUTOMATIC PLATFORM DETECTION
# =====================================

def download_media(url, folder, quality):

    url = url.strip()
    domain = urlparse(url).netloc.lower()

    if "instagram.com" in domain:
        return download_instagram(url, folder)

    elif "youtube.com" in domain or "youtu.be" in domain:
        return download_youtube(url, folder, quality)

    elif "tiktok.com" in domain:
        return download_tiktok(url, folder, quality)

    elif (
        "facebook.com" in domain
        or "fb.watch" in domain
        or "fb.com" in domain
    ):
        return download_facebook(url, folder, quality)

    raise ValueError("Ин платформа дастгирӣ намешавад.")

# =====================================
# START / LANGUAGE SELECTION
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang_tj"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        ],
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ],
    ]

    await update.message.reply_text(
        "🌍 Забон / Язык / Language",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =====================================
# LANGUAGE CALLBACK
# =====================================

async def language_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    lang = query.data.replace("lang_", "")

    if lang not in TEXTS:
        return

    context.user_data["lang"] = lang

    await query.edit_message_text(
        TEXTS[lang]["send_link"]
    )

# =====================================
# HANDLE USER LINKS
# =====================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    lang = context.user_data.get("lang")

    if not lang:
        await start(update, context)
        return

    text = update.message.text.strip()

    match = re.search(
        r"https?://[^\s<>]+",
        text,
        re.IGNORECASE
    )

    if not match:
        await update.message.reply_text(
            TEXTS[lang]["invalid"]
        )
        return

    url = match.group(0).rstrip(".,!?;:)]}")

    domain = urlparse(url).netloc.lower()

    supported = any(
        name in domain
        for name in [
            "instagram.com",
            "youtube.com",
            "youtu.be",
            "tiktok.com",
            "facebook.com",
            "fb.watch",
            "fb.com",
        ]
    )

    if not supported:
        await update.message.reply_text(
            TEXTS[lang]["unsupported"]
        )
        return

    context.user_data["url"] = url

    keyboard = [
        [
            InlineKeyboardButton("⭐ Best", callback_data="quality_best"),
        ],
        [
            InlineKeyboardButton("1080p", callback_data="quality_1080"),
            InlineKeyboardButton("720p", callback_data="quality_720"),
        ],
        [
            InlineKeyboardButton("480p", callback_data="quality_480"),
            InlineKeyboardButton("360p", callback_data="quality_360"),
        ],
    ]

    await update.message.reply_text(
        TEXTS[lang]["quality"],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =====================================
# SEND MEDIA
# =====================================

async def send_media_file(message, filename, media_type, lang):

    size = os.path.getsize(filename)

    if size > MAX_SIZE:
        await message.reply_text(TEXTS[lang]["large"])
        return False

    with open(filename, "rb") as file:

        if media_type == "video":

            await message.reply_video(
                video=file,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30
            )

        else:

            try:
                await message.reply_photo(
                    photo=file,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30
                )

            except Exception:
                file.seek(0)

                await message.reply_document(
                    document=file,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30
                )

    return True

# =====================================
# QUALITY CALLBACK
# =====================================

async def quality_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("lang", "tj")
    url = context.user_data.get("url")

    if not url:
        await query.edit_message_text(
            TEXTS[lang]["invalid"]
        )
        return

    quality = query.data.replace("quality_", "")

    if quality not in ["best", "1080", "720", "480", "360"]:
        return

    await query.edit_message_text(
        TEXTS[lang]["downloading"]
    )

    folder = tempfile.mkdtemp(prefix="turbosave_")

    try:

        results = await asyncio.to_thread(
            download_media,
            url,
            folder,
            quality
        )

        if not results:
            raise ValueError("Ягон файл зеркашӣ нашуд.")

        await query.message.reply_text(
            TEXTS[lang]["sending"]
        )

        sent = 0

        for filename, media_type in results:

            if not os.path.exists(filename):
                continue

            success = await send_media_file(
                query.message,
                filename,
                media_type,
                lang
            )

            if success:
                sent += 1

        await query.message.reply_text(
            TEXTS[lang]["done"]
            + "\n"
            + TEXTS[lang]["sent"].format(sent)
        )

    except Exception as error:

        logger.exception("Download error")

        await query.message.reply_text(
            TEXTS[lang]["failed"].format(str(error)[:500])
        )

    finally:

        shutil.rmtree(folder, ignore_errors=True)

        context.user_data.pop("url", None)

# =====================================
# ERROR HANDLER
# =====================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Telegram error: %s",
        context.error
    )

# =====================================
# MAIN BOT
# =====================================

def main():

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CallbackQueryHandler(
            language_callback,
            pattern=r"^lang_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            quality_callback,
            pattern=r"^quality_"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_error_handler(error_handler)

    logger.info("TurboSave Bot started successfully.")

    app.run_polling(
        drop_pending_updates=False
    )


if __name__ == "__main__":
    main()
