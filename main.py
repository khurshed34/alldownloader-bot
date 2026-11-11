
import os
import re
import sqlite3
import asyncio
import tempfile
import mimetypes
import urllib.request
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
from telegram.error import TelegramError


# ==============================
# SETTINGS
# ==============================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949

MAX_SIZE = 200 * 1024 * 1024
TELEGRAM_MAX_SIZE = 49 * 1024 * 1024

DB_NAME = "bot_stats.db"

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
        "telegram_limit": "⚠️ Файл боргирӣ шуд, аммо аз ҳадди фиристодани Telegram (тақрибан 50 МБ) калонтар аст. Барои фиристодани чунин файл сервери махсус лозим мешавад.",
        "send_url": "🔗 Линки дурусти сайтро фирист.",
        "admin_only": "⛔ Ин фармон танҳо барои админ аст.",
        "stats": "📊 ОМОРИ БОТ\n\n👥 Ҳамагӣ: {users}\n🟢 Имрӯз фаъол: {active}\n📥 Боргириҳо: {downloads}\n\n🌐 Забонҳо:\n🇹🇯 Тоҷикӣ: {tg}\n🇷🇺 Русӣ: {ru}\n🇬🇧 Англисӣ: {en}\n🇮🇷 Форсӣ: {fa}\n🇺🇿 Ӯзбекӣ: {uz}",
        "done": "✅ Тайёр шуд!",
    },
    "ru": {
        "welcome": "👋 Добро пожаловать!\n\n🔗 Отправьте ссылку на видео или фото.",
        "choose": "🌐 Выберите язык:",
        "language": "✅ Язык выбран!",
        "quality": "🎬 Выберите качество видео:",
        "downloading": "⏳ Загрузка началась. Подождите...",
        "failed": "❌ Не удалось загрузить. Возможно, сайт не поддерживается или материал закрытый.",
        "too_big": "❌ Размер файла превышает 200 МБ.",
        "telegram_limit": "⚠️ Файл загружен, но превышает лимит отправки Telegram (около 50 МБ). Для отправки нужен специальный сервер.",
        "send_url": "🔗 Отправьте правильную ссылку.",
        "admin_only": "⛔ Эта команда доступна только администратору.",
        "stats": "📊 СТАТИСТИКА БОТА\n\n👥 Всего: {users}\n🟢 Активны сегодня: {active}\n📥 Загрузки: {downloads}\n\n🌐 Языки:\n🇹🇯 Таджикский: {tg}\n🇷🇺 Русский: {ru}\n🇬🇧 Английский: {en}\n🇮🇷 Персидский: {fa}\n🇺🇿 Узбекский: {uz}",
        "done": "✅ Готово!",
    },
    "en": {
        "welcome": "👋 Welcome!\n\n🔗 Send a video or photo link.",
        "choose": "🌐 Choose your language:",
        "language": "✅ Language selected!",
        "quality": "🎬 Choose video quality:",
        "downloading": "⏳ Download started. Please wait...",
        "failed": "❌ Download failed. The site may not be supported or the content may be private.",
        "too_big": "❌ File size exceeds 200 MB.",
        "telegram_limit": "⚠️ The file was downloaded but exceeds Telegram's upload limit (about 50 MB). A special server is needed to send it.",
        "send_url": "🔗 Please send a valid link.",
        "admin_only": "⛔ This command is only for the administrator.",
        "stats": "📊 BOT STATISTICS\n\n👥 Total users: {users}\n🟢 Active today: {active}\n📥 Downloads: {downloads}\n\n🌐 Languages:\n🇹🇯 Tajik: {tg}\n🇷🇺 Russian: {ru}\n🇬🇧 English: {en}\n🇮🇷 Persian: {fa}\n🇺🇿 Uzbek: {uz}",
        "done": "✅ Done!",
    },
    "fa": {
        "welcome": "👋 خوش آمدید!\n\n🔗 لینک ویدیو یا عکس را بفرستید.",
        "choose": "🌐 زبان خود را انتخاب کنید:",
        "language": "✅ زبان انتخاب شد!",
        "quality": "🎬 کیفیت ویدیو را انتخاب کنید:",
        "downloading": "⏳ دانلود شروع شد. لطفاً صبر کنید...",
        "failed": "❌ دانلود انجام نشد. ممکن است سایت پشتیبانی نشود یا محتوا خصوصی باشد.",
        "too_big": "❌ حجم فایل بیشتر از ۲۰۰ مگابایت است.",
        "telegram_limit": "⚠️ فایل دانلود شد اما از محدودیت ارسال تلگرام (حدود ۵۰ مگابایت) بزرگ‌تر است.",
        "send_url": "🔗 لطفاً لینک معتبر ارسال کنید.",
        "admin_only": "⛔ این دستور فقط برای مدیر است.",
        "stats": "📊 آمار ربات\n\n👥 کل کاربران: {users}\n🟢 فعال امروز: {active}\n📥 دانلودها: {downloads}\n\n🌐 زبان‌ها:\n🇹🇯 تاجیکی: {tg}\n🇷🇺 روسی: {ru}\n🇬🇧 انگلیسی: {en}\n🇮🇷 فارسی: {fa}\n🇺🇿 ازبکی: {uz}",
        "done": "✅ انجام شد!",
    },
    "uz": {
        "welcome": "👋 Xush kelibsiz!\n\n🔗 Video yoki rasm havolasini yuboring.",
        "choose": "🌐 Tilni tanlang:",
        "language": "✅ Til tanlandi!",
        "quality": "🎬 Video sifatini tanlang:",
        "downloading": "⏳ Yuklab olish boshlandi. Kuting...",
        "failed": "❌ Yuklab bo‘lmadi. Sayt qo‘llab-quvvatlanmasligi yoki material yopiq bo‘lishi mumkin.",
        "too_big": "❌ Fayl hajmi 200 MB dan oshdi.",
        "telegram_limit": "⚠️ Fayl yuklandi, ammo Telegram yuborish chegarasidan (taxminan 50 MB) katta.",
        "send_url": "🔗 To‘g‘ri havolani yuboring.",
        "admin_only": "⛔ Bu buyruq faqat administrator uchun.",
        "stats": "📊 BOT STATISTIKASI\n\n👥 Jami: {users}\n🟢 Bugun faol: {active}\n📥 Yuklashlar: {downloads}\n\n🌐 Tillar:\n🇹🇯 Tojikcha: {tg}\n🇷🇺 Ruscha: {ru}\n🇬🇧 Inglizcha: {en}\n🇮🇷 Forscha: {fa}\n🇺🇿 O‘zbekcha: {uz}",
        "done": "✅ Tayyor!",
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

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None

    return url


# ==============================
# DIRECT IMAGE DOWNLOAD
# ==============================

def download_direct_image(url, folder):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
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
            extension = mimetypes.guess_extension(content_type) or ".jpg"

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
                    file.close()
                    file_path.unlink(missing_ok=True)
                    raise ValueError("too_big")

                file.write(chunk)

        return [str(file_path)]


# ==============================
# MEDIA DOWNLOAD
# ==============================

def download_media(url, quality, folder):
    if quality == "auto":
        format_selector = "best/bestvideo+bestaudio"
    else:
        format_selector = (
            f"best[height<={quality}]/best"
        )

    options = {
        "format": format_selector,
        "outtmpl": str(Path(folder) / "%(id)s.%(ext)s"),
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "retries": 2,
        "fragment_retries": 2,
        "max_filesize": MAX_SIZE,
        "merge_output_format": "mp4",
        "overwrites": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
    except Exception:
        pass

    files = []

    for path in Path(folder).iterdir():
        if not path.is_file():
            continue

        if path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue

        if path.stat().st_size == 0:
            continue

        files.append(path)

    if not files:
        direct_files = download_direct_image(url, folder)
        files = [Path(p) for p in direct_files]

    if not files:
        raise RuntimeError("No media found")

    files.sort(key=lambda p: p.name)

    total_size = sum(p.stat().st_size for p in files)

    if total_size > MAX_SIZE:
        raise ValueError("too_big")

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
                    await message.reply_photo(
                        photo=media,
                        caption=text["done"] if sent == 0 else None
                    )

            elif suffix in VIDEO_EXTENSIONS:
                try:
                    with open(file_path, "rb") as media:
                        await message.reply_video(
                            video=media,
                            supports_streaming=True,
                            caption=text["done"] if sent == 0 else None
                        )
                except TelegramError:
                    with open(file_path, "rb") as media:
                        await message.reply_document(
                            document=media,
                            caption=text["done"] if sent == 0 else None
                        )

            else:
                with open(file_path, "rb") as media:
                    await message.reply_document(
                        document=media,
                        caption=text["done"] if sent == 0 else None
                    )

            sent += 1

        except TelegramError:
            continue

    if too_large:
        await message.reply_text(text["telegram_limit"])

    if sent == 0 and not too_large:
        await message.reply_text(text["failed"])

    return sent


# ==============================
# START
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id)

    await update.message.reply_text(
        "🌐 Забон / Язык / Language / زبان / Til",
        reply_markup=language_keyboard()
    )


# ==============================
# LANGUAGE COMMAND
# ==============================

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 Забони худро интихоб кун:",
        reply_markup=language_keyboard()
    )


# ==============================
# ADMIN STATS
# ==============================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        language = get_language(user_id)
        await update.message.reply_text(
            TEXTS[language]["admin_only"]
        )
        return

    stats = get_stats()

    await update.message.reply_text(
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
                await query.message.reply_text(
                    TEXTS[language]["too_big"]
                )
            else:
                await query.message.reply_text(
                    TEXTS[language]["failed"]
                )

        except Exception:
            await query.message.reply_text(
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
    url = extract_url(update.message.text)

    if not url:
        await update.message.reply_text(
            TEXTS[language]["send_url"]
        )
        return

    pending_urls[user_id] = url

    await update.message.reply_text(
        TEXTS[language]["quality"],
        reply_markup=quality_keyboard()
    )


# ==============================
# MAIN
# ==============================

def main():
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. Add it to GitHub Secrets."
        )

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("admin", stats_command))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_link
        )
    )

    print("BOT IS RUNNING...")

    app.run_polling()


if __name__ == "__main__":
    main()
