
import os
import re
import glob
import json
import asyncio
import logging
import tempfile
import shutil
import requests
import yt_dlp
import instaloader

from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
from telegram import (
    Update,
    ReplyKeyboardMarkup,
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
ADMIN_ID = os.getenv("ADMIN_ID")

MAX_SIZE = 49 * 1024 * 1024
DB_FILE = "bot_stats.json"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN ёфт нашуд!")

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
        "welcome": (
            "👋 Хуш омадед ба TurboSave Bot!\n\n"
            "⚡ Зеркашии осон ва босуръат.\n"
            "🔗 Пайванди видео ё аксро фиристед."
        ),
        "download": "📥 Зеркашӣ",
        "quality": "🎬 Сифати видео",
        "language": "🌐 Забон",
        "stats": "📊 Омори бот",
        "help": "ℹ️ Дастур",
        "send_link": "🔗 Лутфан пайванди видео ё аксро фиристед.",
        "choose_quality": "🎬 Сифати дилхоҳро интихоб кунед:",
        "choose_language": "🌐 Забони худро интихоб кунед:",
        "selected": "✅ Танзимот сабт шуд.",
        "working": "⏳ Пайванд қабул шуд. Зеркашӣ оғоз гардид...",
        "finished": "✅ Кор анҷом ёфт!\n📤 Файлҳои фиристодашуда: {}",
        "downloaded": "✅ Зеркашӣ анҷом ёфт!\n📁 Файлҳо: {}\n📤 Фиристодан...",
        "error": "❌ Боргирӣ иҷро нашуд.\n\nСабаб: {}",
        "unsupported": "❌ Ин платформа дастгирӣ намешавад.",
        "too_big": "❌ Ҳаҷми файл аз 49 MB зиёд аст.",
        "admin_only": "❌ Ин бахш танҳо барои администратор аст.",
        "stats_title": "📊 ОМОРИ TURBOSAVE BOT",
        "help_text": (
            "ℹ️ Дастури истифода:\n\n"
            "1. Пайванди TikTok, Instagram ё Facebook-ро фиристед.\n"
            "2. Бот видеоро коркард мекунад.\n"
            "3. Файлро қабул мекунед.\n\n"
            "🎬 Сифатро аз меню интихоб карда метавонед."
        ),
        "quality_saved": "✅ Сифати интихобшуда: {}",
        "platform": "Платформа",
        "users": "Корбарон",
        "downloads": "Зеркашиҳо",
        "errors": "Хатогиҳо",
    },

    "ru": {
        "welcome": (
            "👋 Добро пожаловать в TurboSave Bot!\n\n"
            "⚡ Быстрая загрузка видео и фото.\n"
            "🔗 Отправьте ссылку."
        ),
        "download": "📥 Скачать",
        "quality": "🎬 Качество видео",
        "language": "🌐 Язык",
        "stats": "📊 Статистика",
        "help": "ℹ️ Помощь",
        "send_link": "🔗 Отправьте ссылку на видео или фото.",
        "choose_quality": "🎬 Выберите качество:",
        "choose_language": "🌐 Выберите язык:",
        "selected": "✅ Настройки сохранены.",
        "working": "⏳ Ссылка принята. Начинаю загрузку...",
        "finished": "✅ Готово!\n📤 Отправлено файлов: {}",
        "downloaded": "✅ Загрузка завершена!\n📁 Файлов: {}\n📤 Отправка...",
        "error": "❌ Ошибка загрузки.\n\nПричина: {}",
        "unsupported": "❌ Эта платформа не поддерживается.",
        "too_big": "❌ Размер файла превышает 49 MB.",
        "admin_only": "❌ Только для администратора.",
        "stats_title": "📊 СТАТИСТИКА TURBOSAVE BOT",
        "help_text": (
            "ℹ️ Инструкция:\n\n"
            "1. Отправьте ссылку TikTok, Instagram или Facebook.\n"
            "2. Бот обработает видео.\n"
            "3. Получите файл.\n\n"
            "🎬 Качество можно выбрать в меню."
        ),
        "quality_saved": "✅ Выбрано качество: {}",
        "platform": "Платформа",
        "users": "Пользователи",
        "downloads": "Загрузки",
        "errors": "Ошибки",
    },

    "en": {
        "welcome": (
            "👋 Welcome to TurboSave Bot!\n\n"
            "⚡ Fast video and photo downloads.\n"
            "🔗 Send a video or photo link."
        ),
        "download": "📥 Download",
        "quality": "🎬 Video quality",
        "language": "🌐 Language",
        "stats": "📊 Bot statistics",
        "help": "ℹ️ Help",
        "send_link": "🔗 Please send a video or photo link.",
        "choose_quality": "🎬 Choose video quality:",
        "choose_language": "🌐 Choose your language:",
        "selected": "✅ Settings saved.",
        "working": "⏳ Link received. Downloading...",
        "finished": "✅ Completed!\n📤 Files sent: {}",
        "downloaded": "✅ Download completed!\n📁 Files: {}\n📤 Sending...",
        "error": "❌ Download failed.\n\nReason: {}",
        "unsupported": "❌ This platform is not supported.",
        "too_big": "❌ File size exceeds 49 MB.",
        "admin_only": "❌ Administrator only.",
        "stats_title": "📊 TURBOSAVE BOT STATISTICS",
        "help_text": (
            "ℹ️ Instructions:\n\n"
            "1. Send a TikTok, Instagram or Facebook link.\n"
            "2. The bot processes the media.\n"
            "3. Receive your file.\n\n"
            "🎬 Choose quality from the menu."
        ),
        "quality_saved": "✅ Selected quality: {}",
        "platform": "Platform",
        "users": "Users",
        "downloads": "Downloads",
        "errors": "Errors",
    }
}

QUALITY_NAMES = {
    "best": "🔝 Best",
    "1080": "1080p",
    "720": "720p",
    "480": "480p",
    "360": "360p",
}

# =====================================
# DATABASE
# =====================================

def load_stats():
    default = {
        "users": [],
        "downloads": 0,
        "errors": 0,
        "platforms": {
            "TikTok": 0,
            "Instagram": 0,
            "Facebook": 0
        }
    }

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        for key, value in default.items():
            if key not in data:
                data[key] = value

        return data

    except (FileNotFoundError, json.JSONDecodeError):
        return default


stats = load_stats()


def save_stats():
    temp_file = DB_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    os.replace(temp_file, DB_FILE)


def register_user(user_id):
    user_id = str(user_id)

    if user_id not in stats["users"]:
        stats["users"].append(user_id)
        save_stats()


def record_download(platform):
    stats["downloads"] += 1
    stats["platforms"][platform] += 1
    save_stats()


def record_error():
    stats["errors"] += 1
    save_stats()


# =====================================
# USER SETTINGS
# =====================================

def get_lang(context):
    return context.user_data.get("lang", "tj")


def tr(context, key):
    return TEXTS[get_lang(context)][key]


def is_admin(user_id):
    return bool(
        ADMIN_ID
        and str(user_id) == str(ADMIN_ID)
    )


# =====================================
# MAIN KEYBOARD
# =====================================

def main_keyboard(context, user_id):

    t = TEXTS[get_lang(context)]

    keyboard = [
        [
            "🎵 TikTok",
            "📸 Instagram"
        ],
        [
            "📘 Facebook",
            t["quality"]
        ],
        [
            t["language"],
            t["help"]
        ]
    ]

    if is_admin(user_id):
        keyboard.append([t["stats"]])

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# =====================================
# QUALITY KEYBOARD
# =====================================

def quality_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔝 Best",
                callback_data="quality_best"
            ),
            InlineKeyboardButton(
                "1080p",
                callback_data="quality_1080"
            )
        ],
        [
            InlineKeyboardButton(
                "720p",
                callback_data="quality_720"
            ),
            InlineKeyboardButton(
                "480p",
                callback_data="quality_480"
            )
        ],
        [
            InlineKeyboardButton(
                "360p",
                callback_data="quality_360"
            )
        ]
    ])


# =====================================
# LANGUAGE KEYBOARD
# =====================================

def language_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🇹🇯 Тоҷикӣ",
                callback_data="lang_tj"
            )
        ],
        [
            InlineKeyboardButton(
                "🇷🇺 Русский",
                callback_data="lang_ru"
            )
        ],
        [
            InlineKeyboardButton(
                "🇬🇧 English",
                callback_data="lang_en"
            )
        ]
    ])


# =====================================
# START
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    register_user(user.id)

    context.user_data.setdefault("lang", "tj")
    context.user_data.setdefault("quality", "best")

    await update.message.reply_text(
        tr(context, "welcome"),
        reply_markup=main_keyboard(context, user.id)
    )


# =====================================
# SETTINGS CALLBACKS
# =====================================

async def callback_handler(update, context):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    register_user(user_id)

    if data.startswith("lang_"):

        lang = data.replace("lang_", "")

        if lang not in TEXTS:
            return

        context.user_data["lang"] = lang

        await query.edit_message_text(
            TEXTS[lang]["selected"]
        )

        await context.bot.send_message(
            chat_id=user_id,
            text=TEXTS[lang]["welcome"],
            reply_markup=main_keyboard(context, user_id)
        )

    elif data.startswith("quality_"):

        quality = data.replace("quality_", "")

        if quality not in QUALITY_NAMES:
            return

        context.user_data["quality"] = quality

        await query.edit_message_text(
            tr(context, "quality_saved").format(
                QUALITY_NAMES[quality]
            )
        )


# =====================================
# DIRECT DOWNLOAD
# =====================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    )
}


def download_file(url, filename):

    response = requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=90
    )

    response.raise_for_status()

    total = 0

    with open(filename, "wb") as f:
        for chunk in response.iter_content(1024 * 1024):

            if chunk:
                total += len(chunk)

                if total > MAX_SIZE:
                    raise ValueError(
                        "Файл аз 49 MB калон аст."
                    )

                f.write(chunk)

    if total == 0:
        raise ValueError("Файл холӣ аст.")


# =====================================
# FIND FILE
# =====================================

def find_downloaded_file(folder, prefix):

    files = glob.glob(
        os.path.join(folder, prefix + "*")
    )

    files = [
        f for f in files
        if os.path.isfile(f)
        and not f.endswith(
            (".part", ".ytdl", ".json")
        )
    ]

    if not files:
        raise ValueError("Файл ёфт нашуд.")

    return max(files, key=os.path.getsize)


# =====================================
# YT-DLP QUALITY FORMAT
# =====================================

def get_video_format(quality):

    if quality == "best":
        return "best[ext=mp4]/best"

    height = int(quality)

    return (
        f"best[height<={height}][ext=mp4]/"
        f"best[height<={height}]/best"
    )


# =====================================
# YT-DLP DOWNLOADER
# =====================================

def download_with_ytdlp(url, folder, prefix, quality):

    os.makedirs(folder, exist_ok=True)

    output = os.path.join(
        folder,
        prefix + "_%(id)s.%(ext)s"
    )

    options = {
        "format": get_video_format(quality),
        "outtmpl": output,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 40,
        "overwrites": True,
        "max_filesize": MAX_SIZE,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)

    filename = find_downloaded_file(
        folder,
        prefix
    )

    if os.path.getsize(filename) > MAX_SIZE:
        raise ValueError("Файл аз 49 MB калон аст.")

    return [(filename, "video")]


# =====================================
# INSTAGRAM
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

    elif post.is_video:

        filename = os.path.join(
            folder,
            "instagram_video.mp4"
        )

        download_file(post.video_url, filename)
        results.append((filename, "video"))

    else:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg"
        )

        download_file(post.url, filename)
        results.append((filename, "photo"))

    return results


# =====================================
# TIKTOK
# =====================================

def download_tiktok(url, folder, quality):

    if not re.search(
        r"(tiktok\.com|vm\.tiktok\.com)",
        url,
        re.IGNORECASE
    ):
        raise ValueError("Пайванди TikTok нодуруст аст.")

    return download_with_ytdlp(
        url,
        folder,
        "tiktok",
        quality
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

        key = (
            data.get("property")
            or data.get("name")
        )

        value = data.get("content")

        if key and value:
            self.meta[key.lower()] = value


# =====================================
# FACEBOOK PHOTO
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
        raise ValueError(
            "Акси оммавии Facebook ёфт нашуд."
        )

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
        raise ValueError("Файли акс нодуруст аст.")

    extension = ".jpg"

    if "png" in content_type:
        extension = ".png"
    elif "webp" in content_type:
        extension = ".webp"

    filename = os.path.join(
        folder,
        "facebook_photo" + extension
    )

    total = 0

    with open(filename, "wb") as f:
        for chunk in image_response.iter_content(1024 * 1024):
            if chunk:
                total += len(chunk)

                if total > MAX_SIZE:
                    raise ValueError("Акс аз 49 MB калон аст.")

                f.write(chunk)

    return [(filename, "photo")]


# =====================================
# FACEBOOK
# =====================================

def download_facebook(url, folder, quality):

    if not re.search(
        r"(facebook\.com|fb\.watch|fb\.com)",
        url,
        re.IGNORECASE
    ):
        raise ValueError("Пайванди Facebook нодуруст аст.")

    try:

        return download_with_ytdlp(
            url,
            folder,
            "facebook",
            quality
        )

    except Exception as video_error:

        logger.warning(
            "Facebook video failed: %s",
            video_error
        )

        try:

            return download_facebook_photo(
                url,
                folder
            )

        except Exception as photo_error:

            raise ValueError(
                "Facebook зеркашӣ нашуд.\n"
                "Видео: " + str(video_error)[:200]
                + "\nАкс: " + str(photo_error)[:200]
            )


# =====================================
# PLATFORM DETECTION
# =====================================

def download_media(url, folder, quality):

    domain = urlparse(url).netloc.lower()

    if "instagram.com" in domain:
        return "Instagram", download_instagram(url, folder)

    if "tiktok.com" in domain:
        return "TikTok", download_tiktok(url, folder, quality)

    if (
        "facebook.com" in domain
        or "fb.watch" in domain
        or "fb.com" in domain
    ):
        return "Facebook", download_facebook(url, folder, quality)

    raise ValueError(
        "Танҳо TikTok, Instagram ва Facebook дастгирӣ мешаванд."
    )


# =====================================
# SEND FILE
# =====================================

async def send_media_file(update, filename, media_type):

    if os.path.getsize(filename) > MAX_SIZE:
        raise ValueError("Файл аз 49 MB калон аст.")

    with open(filename, "rb") as file:

        if media_type == "video":

            await update.message.reply_video(
                video=file,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30
            )

        else:

            try:

                await update.message.reply_photo(
                    photo=file,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30
                )

            except Exception:

                file.seek(0)

                await update.message.reply_document(
                    document=file,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30
                )


# =====================================
# BOT STATISTICS
# =====================================

async def show_stats(update, context):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await update.message.reply_text(
            tr(context, "admin_only")
        )

        return

    s = stats

    message = (
        f"{tr(context, 'stats_title')}\n\n"
        f"👥 {tr(context, 'users')}: {len(s['users'])}\n"
        f"📥 {tr(context, 'downloads')}: {s['downloads']}\n"
        f"❌ {tr(context, 'errors')}: {s['errors']}\n\n"
        f"🎵 TikTok: {s['platforms']['TikTok']}\n"
        f"📸 Instagram: {s['platforms']['Instagram']}\n"
        f"📘 Facebook: {s['platforms']['Facebook']}"
    )

    await update.message.reply_text(message)


# =====================================
# HANDLE MENU
# =====================================

async def handle_menu(update, context):

    message = update.message
    user = update.effective_user

    register_user(user.id)

    text = message.text
    t = TEXTS[get_lang(context)]

    if text == t["quality"] or text == "🎬 Сифати видео" or text == "🎬 Качество видео" or text == "🎬 Video quality":

        await message.reply_text(
            tr(context, "choose_quality"),
            reply_markup=quality_keyboard()
        )

        return

    if text == t["language"] or text in ("🌐 Забон", "🌐 Язык", "🌐 Language"):

        await message.reply_text(
            tr(context, "choose_language"),
            reply_markup=language_keyboard()
        )

        return

    if text == t["help"] or text in ("ℹ️ Дастур", "ℹ️ Помощь", "ℹ️ Help"):

        await message.reply_text(
            t["help_text"]
        )

        return

    if text == t["stats"] or text in ("📊 Омори бот", "📊 Статистика", "📊 Bot statistics"):

        await show_stats(update, context)
        return

    if text in (
        "📥 Зеркашӣ",
        "📥 Скачать",
        "📥 Download",
        "🎵 TikTok",
        "📸 Instagram",
        "📘 Facebook"
    ):

        await message.reply_text(
            tr(context, "send_link")
        )


# =====================================
# HANDLE LINKS
# =====================================

async def handle_message(update, context):

    if not update.message or not update.message.text:
        return

    user = update.effective_user
    register_user(user.id)

    text = update.message.text.strip()

    # Menu actions
    if not re.search(r"https?://", text, re.IGNORECASE):
        await handle_menu(update, context)
        return

    match = re.search(
        r"https?://[^\s<>]+",
        text,
        re.IGNORECASE
    )

    if not match:
        await update.message.reply_text(
            tr(context, "send_link")
        )
        return

    url = match.group(0).rstrip(
        ".,!?;:)]}"
    )

    status = await update.message.reply_text(
        tr(context, "working")
    )

    folder = tempfile.mkdtemp(
        prefix="turbosave_"
    )

    quality = context.user_data.get(
        "quality",
        "best"
    )

    try:

        platform, results = await asyncio.to_thread(
            download_media,
            url,
            folder,
            quality
        )

        if not results:
            raise ValueError("Ягон файл зеркашӣ нашуд.")

        await status.edit_text(
            tr(context, "downloaded").format(len(results))
        )

        sent = 0

        for filename, media_type in results:

            if not os.path.exists(filename):
                continue

            await send_media_file(
                update,
                filename,
                media_type
            )

            sent += 1

        if sent:
            record_download(platform)

        await status.edit_text(
            tr(context, "finished").format(sent)
        )

    except Exception as error:

        logger.exception("Download error")

        record_error()

        await status.edit_text(
            tr(context, "error").format(
                str(error)[:600]
            )
        )

    finally:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )


# =====================================
# ERROR HANDLER
# =====================================

async def error_handler(update, context):

    logger.error(
        "Telegram error: %s",
        context.error
    )


# =====================================
# MAIN
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
        CallbackQueryHandler(callback_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_error_handler(error_handler)

    logger.info("TurboSave Bot started!")

    app.run_polling(
        drop_pending_updates=False
    )


if __name__ == "__main__":
    main()
