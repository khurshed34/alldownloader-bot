
import os
import re
import sqlite3
import asyncio
import tempfile
import mimetypes
import urllib.request
import logging

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

import yt_dlp

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError, BadRequest


# ==============================
# SETTINGS
# ==============================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949

MAX_SIZE = 200 * 1024 * 1024
TELEGRAM_MAX_SIZE = 49 * 1024 * 1024

DB_NAME = "bot_stats.db"

DELETE_AFTER = 47 * 60 * 60
DELETE_CHECK_INTERVAL = 60

pending_urls = {}

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mov",
    ".avi", ".m4v", ".flv", ".3gp"
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".gif", ".bmp", ".avif", ".heic"
}

MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


# ==============================
# LOGGING
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

logger = logging.getLogger(__name__)


# ==============================
# LANGUAGES
# ==============================

TEXTS = {
    "tg": {
        "welcome": "👋 Хуш омадӣ!\n\n🔗 Линки видео ё суратро фирист.",
        "choose": "🌐 Забони худро интихоб кун:",
        "language": "✅ Забон интихоб шуд!",
        "quality": "🎬 Сифати видеоро интихоб кун:",
        "downloading": "⏳ Боргирӣ сар шуд. Каме интизор шав...",
        "failed": "❌ Боргирӣ нашуд. Эҳтимол сайт дастгирӣ намешавад ё мавод хусусӣ аст.",
        "too_big": "❌ Андозаи файл аз ҳадди 200 МБ зиёд аст.",
        "telegram_limit": "⚠️ Файл аз ҳадди фиристодани Telegram калонтар аст.",
        "send_url": "🔗 Линки дурусти сайтро фирист.",
        "admin_only": "⛔ Ин фармон танҳо барои админ аст.",
        "done": "✅ Тайёр шуд!",
        "stats": "📊 ОМОРИ БОТ\n\n👥 Ҳамагӣ: {users}\n🟢 Имрӯз фаъол: {active}\n📥 Боргириҳо: {downloads}\n\n🌐 Забонҳо:\n🇹🇯 Тоҷикӣ: {tg}\n🇷🇺 Русӣ: {ru}\n🇬🇧 Англисӣ: {en}\n🇮🇷 Форсӣ: {fa}\n🇺🇿 Ӯзбекӣ: {uz}",
    },
    "ru": {
        "welcome": "👋 Добро пожаловать!\n\n🔗 Отправьте ссылку на видео или фото.",
        "choose": "🌐 Выберите язык:",
        "language": "✅ Язык выбран!",
        "quality": "🎬 Выберите качество видео:",
        "downloading": "⏳ Загрузка началась. Подождите...",
        "failed": "❌ Не удалось загрузить. Возможно, сайт не поддерживается или материал закрытый.",
        "too_big": "❌ Размер файла превышает 200 МБ.",
        "telegram_limit": "⚠️ Файл превышает лимит отправки Telegram.",
        "send_url": "🔗 Отправьте правильную ссылку.",
        "admin_only": "⛔ Эта команда доступна только администратору.",
        "done": "✅ Готово!",
        "stats": "📊 СТАТИСТИКА БОТА\n\n👥 Всего: {users}\n🟢 Активны сегодня: {active}\n📥 Загрузки: {downloads}\n\n🌐 Языки:\n🇹🇯 Таджикский: {tg}\n🇷🇺 Русский: {ru}\n🇬🇧 Английский: {en}\n🇮🇷 Персидский: {fa}\n🇺🇿 Узбекский: {uz}",
    },
    "en": {
        "welcome": "👋 Welcome!\n\n🔗 Send a video or photo link.",
        "choose": "🌐 Choose your language:",
        "language": "✅ Language selected!",
        "quality": "🎬 Choose video quality:",
        "downloading": "⏳ Download started. Please wait...",
        "failed": "❌ Download failed. The site may not be supported or the content may be private.",
        "too_big": "❌ File size exceeds 200 MB.",
        "telegram_limit": "⚠️ File exceeds Telegram's upload limit.",
        "send_url": "🔗 Please send a valid link.",
        "admin_only": "⛔ Admin only.",
        "done": "✅ Done!",
        "stats": "📊 BOT STATISTICS\n\n👥 Total: {users}\n🟢 Active today: {active}\n📥 Downloads: {downloads}\n\n🌐 Languages:\n🇹🇯 Tajik: {tg}\n🇷🇺 Russian: {ru}\n🇬🇧 English: {en}\n🇮🇷 Persian: {fa}\n🇺🇿 Uzbek: {uz}",
    },
    "fa": {
        "welcome": "👋 خوش آمدید!\n\n🔗 لینک ویدیو یا عکس را بفرستید.",
        "choose": "🌐 زبان خود را انتخاب کنید:",
        "language": "✅ زبان انتخاب شد!",
        "quality": "🎬 کیفیت ویدیو را انتخاب کنید:",
        "downloading": "⏳ دانلود شروع شد. لطفاً صبر کنید...",
        "failed": "❌ دانلود انجام نشد. ممکن است سایت پشتیبانی نشود یا محتوا خصوصی باشد.",
        "too_big": "❌ حجم فایل بیشتر از ۲۰۰ مگابایت است.",
        "telegram_limit": "⚠️ فایل از محدودیت ارسال تلگرام بزرگ‌تر است.",
        "send_url": "🔗 لطفاً لینک معتبر ارسال کنید.",
        "admin_only": "⛔ این دستور فقط برای مدیر است.",
        "done": "✅ انجام شد!",
        "stats": "📊 آمار ربات\n\n👥 کل کاربران: {users}\n🟢 فعال امروز: {active}\n📥 دانلودها: {downloads}\n\n🌐 زبان‌ها:\n🇹🇯 تاجیکی: {tg}\n🇷🇺 روسی: {ru}\n🇬🇧 انگلیسی: {en}\n🇮🇷 فارسی: {fa}\n🇺🇿 ازبکی: {uz}",
    },
    "uz": {
        "welcome": "👋 Xush kelibsiz!\n\n🔗 Video yoki rasm havolasini yuboring.",
        "choose": "🌐 Tilni tanlang:",
        "language": "✅ Til tanlandi!",
        "quality": "🎬 Video sifatini tanlang:",
        "downloading": "⏳ Yuklab olish boshlandi. Kuting...",
        "failed": "❌ Yuklab bo‘lmadi. Sayt qo‘llab-quvvatlanmasligi yoki material yopiq bo‘lishi mumkin.",
        "too_big": "❌ Fayl hajmi 200 MB dan oshdi.",
        "telegram_limit": "⚠️ Fayl Telegram yuborish chegarasidan katta.",
        "send_url": "🔗 To‘g‘ri havolani yuboring.",
        "admin_only": "⛔ Bu buyruq faqat administrator uchun.",
        "done": "✅ Tayyor!",
        "stats": "📊 BOT STATISTIKASI\n\n👥 Jami: {users}\n🟢 Bugun faol: {active}\n📥 Yuklashlar: {downloads}\n\n🌐 Tillar:\n🇹🇯 Tojikcha: {tg}\n🇷🇺 Ruscha: {ru}\n🇬🇧 Inglizcha: {en}\n🇮🇷 Forscha: {fa}\n🇺🇿 O‘zbekcha: {uz}",
    },
}


# ==============================
# DATABASE
# ==============================

def db_connect():
    return sqlite3.connect(DB_NAME)


def init_db():
    with db_connect() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'tg',
                last_active TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                url TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_deletions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                delete_at REAL NOT NULL,
                UNIQUE(chat_id, message_id)
            )
        """)


def save_user(user_id):
    today = datetime.now(timezone.utc).date().isoformat()

    with db_connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users
            (user_id, language, last_active)
            VALUES (?, 'tg', ?)
        """, (user_id, today))

        conn.execute("""
            UPDATE users SET last_active = ?
            WHERE user_id = ?
        """, (today, user_id))


def get_language(user_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT language FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if row and row[0] in TEXTS:
        return row[0]

    return "tg"


def set_language(user_id, language):
    if language not in TEXTS:
        return

    today = datetime.now(timezone.utc).date().isoformat()

    with db_connect() as conn:
        conn.execute("""
            INSERT INTO users (user_id, language, last_active)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                language = excluded.language,
                last_active = excluded.last_active
        """, (user_id, language, today))


def save_download(user_id, url):
    now = datetime.now(timezone.utc).isoformat()

    with db_connect() as conn:
        conn.execute("""
            INSERT INTO downloads (user_id, url, created_at)
            VALUES (?, ?, ?)
        """, (user_id, url, now))


def get_stats():
    today = datetime.now(timezone.utc).date().isoformat()

    with db_connect() as conn:
        users = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        active = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_active = ?",
            (today,)
        ).fetchone()[0]

        downloads = conn.execute(
            "SELECT COUNT(*) FROM downloads"
        ).fetchone()[0]

        language_counts = dict(
            conn.execute("""
                SELECT language, COUNT(*)
                FROM users
                GROUP BY language
            """).fetchall()
        )

    return {
        "users": users,
        "active": active,
        "downloads": downloads,
        "tg": language_counts.get("tg", 0),
        "ru": language_counts.get("ru", 0),
        "en": language_counts.get("en", 0),
        "fa": language_counts.get("fa", 0),
        "uz": language_counts.get("uz", 0),
    }


# ==============================
# AUTOMATIC MESSAGE DELETION
# ==============================

async def track_message(message):
    if not message:
        return

    delete_at = (
        datetime.now(timezone.utc).timestamp()
        + DELETE_AFTER
    )

    try:
        with db_connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO scheduled_deletions
                (chat_id, message_id, delete_at)
                VALUES (?, ?, ?)
            """, (
                message.chat_id,
                message.message_id,
                delete_at
            ))
    except Exception:
        logger.exception("Could not schedule message deletion")


async def reply_tracked(message, text, **kwargs):
    sent = await message.reply_text(text, **kwargs)
    await track_message(sent)
    return sent


async def deletion_worker(application):
    logger.info("Message deletion worker started")

    while True:
        now = datetime.now(timezone.utc).timestamp()

        try:
            with db_connect() as conn:
                rows = conn.execute("""
                    SELECT id, chat_id, message_id
                    FROM scheduled_deletions
                    WHERE delete_at <= ?
                """, (now,)).fetchall()

            for row_id, chat_id, message_id in rows:
                try:
                    await application.bot.delete_message(
                        chat_id=chat_id,
                        message_id=message_id
                    )

                    logger.info(
                        "Message deleted: chat=%s message=%s",
                        chat_id,
                        message_id
                    )

                except BadRequest as error:
                    logger.warning(
                        "Message cannot be deleted: %s", error
                    )

                except TelegramError:
                    logger.exception(
                        "Temporary Telegram deletion error"
                    )

                    # Retry after five minutes
                    with db_connect() as conn:
                        conn.execute("""
                            UPDATE scheduled_deletions
                            SET delete_at = ?
                            WHERE id = ?
                        """, (
                            now + 300,
                            row_id
                        ))
                    continue

                with db_connect() as conn:
                    conn.execute(
                        "DELETE FROM scheduled_deletions WHERE id = ?",
                        (row_id,)
                    )

        except Exception:
            logger.exception("Deletion worker error")

        await asyncio.sleep(DELETE_CHECK_INTERVAL)


# ==============================
# KEYBOARDS
# ==============================

def language_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang:tg"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
        ],
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
            InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang:fa"),
        ],
        [
            InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="lang:uz"),
        ],
    ])


def quality_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 144p", callback_data="quality:144"),
            InlineKeyboardButton("🎬 360p", callback_data="quality:360"),
        ],
        [
            InlineKeyboardButton("🎬 480p", callback_data="quality:480"),
            InlineKeyboardButton("🎬 720p", callback_data="quality:720"),
        ],
        [
            InlineKeyboardButton("🔥 1080p", callback_data="quality:1080"),
            InlineKeyboardButton("⚡ Auto", callback_data="quality:auto"),
        ],
    ])


# ==============================
# URL HELPERS
# ==============================

def extract_url(text):
    match = re.search(r"https?://[^\s]+", text or "")

    if not match:
        return None

    url = match.group(0).rstrip(".,!?)]}>\"'")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return None

    if not parsed.hostname:
        return None

    return url


# ==============================
# DIRECT IMAGE DOWNLOAD
# ==============================

def download_direct_image(url, folder):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:

        content_type = response.headers.get(
            "Content-Type", ""
        ).split(";")[0].lower()

        if not content_type.startswith("image/"):
            return []

        length = response.headers.get("Content-Length")

        if length and int(length) > MAX_SIZE:
            raise ValueError("too_big")

        extension = Path(urlparse(url).path).suffix.lower()

        if extension not in IMAGE_EXTENSIONS:
            extension = mimetypes.guess_extension(
                content_type
            ) or ".jpg"

        if extension == ".jpe":
            extension = ".jpg"

        file_path = Path(folder) / ("direct_image" + extension)

        total = 0

        with open(file_path, "wb") as file:
            while True:
                chunk = response.read(1024 * 1024)

                if not chunk:
                    break

                total += len(chunk)

                if total > MAX_SIZE:
                    raise ValueError("too_big")

                file.write(chunk)

        return [str(file_path)]


# ==============================
# MEDIA DOWNLOAD
# ==============================

def download_media(url, quality, folder):

    if quality == "auto":
        format_selector = "best"
    else:
        format_selector = f"best[height<={quality}]/best"

    options = {
        "format": format_selector,
        "outtmpl": str(Path(folder) / "%(id)s.%(ext)s"),
        "noplaylist": False,
        "quiet": True,
        "no_warnings": False,
        "ignoreerrors": False,
        "retries": 5,
        "extractor_retries": 3,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "max_filesize": MAX_SIZE,
        "merge_output_format": "mp4",
        "overwrites": True,
    }

    download_error = None

    try:
        logger.info("Starting download: %s", url)

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)

    except Exception as error:
        download_error = str(error)

        logger.exception(
            "MEDIA DOWNLOAD FAILED: %s", url
        )

    files = []

    for path in Path(folder).iterdir():
        if not path.is_file():
            continue

        if path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue

        if path.stat().st_size == 0:
            continue

        files.append(path)

    # Try direct image URL if extractor found nothing
    if not files:
        try:
            direct_files = download_direct_image(url, folder)
            files = [Path(p) for p in direct_files]

        except Exception:
            logger.exception(
                "DIRECT IMAGE DOWNLOAD FAILED: %s", url
            )

    if not files:
        raise RuntimeError(
            f"No media found. Downloader error: {download_error}"
        )

    files.sort(key=lambda p: p.name)

    total_size = sum(p.stat().st_size for p in files)

    if total_size > MAX_SIZE:
        raise ValueError("too_big")

    logger.info(
        "Download successful: %s files",
        len(files)
    )

    return files


# ==============================
# SEND MEDIA
# ==============================

async def send_downloaded_files(message, files, language):

    text = TEXTS[language]

    sent = 0
    too_large = False

    for file_path in files:

        size = file_path.stat().st_size

        if size > TELEGRAM_MAX_SIZE:
            too_large = True
            continue

        suffix = file_path.suffix.lower()

        try:

            if suffix in {".jpg", ".jpeg", ".png"} and size <= 10 * 1024 * 1024:

                with open(file_path, "rb") as media:
                    sent_message = await message.reply_photo(
                        photo=media,
                        caption=text["done"] if sent == 0 else None
                    )

            elif suffix in VIDEO_EXTENSIONS:

                try:
                    with open(file_path, "rb") as media:
                        sent_message = await message.reply_video(
                            video=media,
                            supports_streaming=True,
                            caption=text["done"] if sent == 0 else None
                        )

                except TelegramError:
                    with open(file_path, "rb") as media:
                        sent_message = await message.reply_document(
                            document=media,
                            caption=text["done"] if sent == 0 else None
                        )

            else:

                with open(file_path, "rb") as media:
                    sent_message = await message.reply_document(
                        document=media,
                        caption=text["done"] if sent == 0 else None
                    )

            await track_message(sent_message)
            sent += 1

        except TelegramError:
            logger.exception(
                "Telegram media sending failed: %s",
                file_path
            )

    if too_large:
        await reply_tracked(
            message,
            text["telegram_limit"]
        )

    if sent == 0 and not too_large:
        await reply_tracked(
            message,
            text["failed"]
        )

    return sent


# ==============================
# START
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    save_user(user_id)

    msg = await update.message.reply_text(
        "🌐 Забон / Язык / Language / زبان / Til",
        reply_markup=language_keyboard()
    )

    await track_message(msg)


# ==============================
# LANGUAGE COMMAND
# ==============================

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    msg = await update.message.reply_text(
        "🌐 Забони худро интихоб кун:",
        reply_markup=language_keyboard()
    )

    await track_message(msg)


# ==============================
# ADMIN STATS
# ==============================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        language = get_language(user_id)

        await reply_tracked(
            update.message,
            TEXTS[language]["admin_only"]
        )
        return

    stats = get_stats()

    await reply_tracked(
        update.message,
        TEXTS["tg"]["stats"].format(**stats)
    )


# ==============================
# CALLBACKS
# ==============================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data.startswith("lang:"):

        language = data.split(":", 1)[1]

        if language not in TEXTS:
            return

        set_language(user_id, language)

        await query.edit_message_text(
            TEXTS[language]["language"] + "\n\n" +
            TEXTS[language]["welcome"]
        )

        return

    if data.startswith("quality:"):

        language = get_language(user_id)
        quality = data.split(":", 1)[1]

        url = pending_urls.get(user_id)

        if not url:
            await query.edit_message_text(
                TEXTS[language]["failed"]
            )
            return

        await query.edit_message_text(
            TEXTS[language]["downloading"]
        )

        try:

            with tempfile.TemporaryDirectory() as folder:

                files = await asyncio.to_thread(
                    download_media,
                    url,
                    quality,
                    folder
                )

                sent = await send_downloaded_files(
                    query.message,
                    files,
                    language
                )

                if sent > 0:
                    save_download(user_id, url)

        except ValueError as error:

            if str(error) == "too_big":
                await reply_tracked(
                    query.message,
                    TEXTS[language]["too_big"]
                )
            else:
                logger.exception("Download value error")

                await reply_tracked(
                    query.message,
                    TEXTS[language]["failed"]
                )

        except Exception:

            logger.exception(
                "DOWNLOAD FAILED FOR USER %s URL %s",
                user_id,
                url
            )

            await reply_tracked(
                query.message,
                TEXTS[language]["failed"]
            )

        finally:
            pending_urls.pop(user_id, None)


# ==============================
# RECEIVE LINKS
# ==============================

async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    save_user(user_id)

    language = get_language(user_id)

    await track_message(update.message)

    url = extract_url(update.message.text)

    if not url:
        await reply_tracked(
            update.message,
            TEXTS[language]["send_url"]
        )
        return

    pending_urls[user_id] = url

    msg = await update.message.reply_text(
        TEXTS[language]["quality"],
        reply_markup=quality_keyboard()
    )

    await track_message(msg)


# ==============================
# APPLICATION STARTUP
# ==============================

async def post_init(application):

    application.create_task(
        deletion_worker(application)
    )

    logger.info("BOT STARTED SUCCESSFULLY")


# ==============================
# MAIN
# ==============================

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add it to GitHub Secrets."
        )

    init_db()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("admin", stats_command))

    app.add_handler(
        CallbackQueryHandler(callback_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_link
        )
    )

    logger.info("BOT IS RUNNING...")

    app.run_polling()


if __name__ == "__main__":
    main()
