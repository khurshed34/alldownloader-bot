
import os
import re
import sqlite3
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================ SETTINGS ================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949

DB_FILE = "bot_stats.db"

# Download limit: 200 MB
MAX_SIZE = 200 * 1024 * 1024

# Standard Telegram Bot API upload limit: keep below 50 MB
TELEGRAM_MAX_SIZE = 49_000_000

if not TOKEN:
    raise RuntimeError("BOT_TOKEN дар GitHub Secrets ёфт нашуд!")

# ================ DATABASE ================

def db():
    return sqlite3.connect(DB_FILE)

def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'tg',
                last_active TEXT
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT
            )
        """)

def register_user(user_id):
    today = datetime.now(timezone.utc).date().isoformat()

    with db() as con:
        con.execute("""
            INSERT OR IGNORE INTO users
            (user_id, language, last_active)
            VALUES (?, 'tg', ?)
        """, (user_id, today))

        con.execute("""
            UPDATE users SET last_active = ?
            WHERE user_id = ?
        """, (today, user_id))

def get_language(user_id):
    with db() as con:
        result = con.execute(
            "SELECT language FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    return result[0] if result else "tg"

def set_language(user_id, language):
    with db() as con:
        con.execute(
            "UPDATE users SET language = ? WHERE user_id = ?",
            (language, user_id)
        )

def add_download(user_id):
    with db() as con:
        con.execute(
            "INSERT INTO downloads (user_id, created_at) VALUES (?, ?)",
            (user_id, datetime.now(timezone.utc).isoformat())
        )

# ================ LANGUAGES ================

TEXT = {
    "tg": {
        "welcome": "🎬 Салом! Ба боти зеркашӣ хуш омадӣ!\n\n📥 Линки TikTok, Instagram ё Facebook-ро фирист.",
        "quality": "🎥 Сифати дилхоҳро интихоб кун:",
        "downloading": "⏳ Зеркашӣ шуда истодааст...",
        "done": "✅ Файл фиристода шуд!",
        "error": "❌ Хатогӣ! Линкро санҷида, боз кӯшиш кун.",
        "unsupported": "❌ Ин сайт дастгирӣ намешавад.",
        "large": "❌ Файл аз маҳдудияти фиристодани Telegram калон аст.",
        "choose": "🌐 Забонро интихоб кун:",
        "denied": "⛔ Ин фармон танҳо барои админ аст.",
        "admin": "🔐 ОМОРИ АДМИН\n\n👥 Ҳамагӣ истифодабарандагон: {users}\n🟢 Фаъол имрӯз: {active}\n🎬 Ҳамагӣ зеркашиҳо: {downloads}\n\n🌐 Забонҳо:\n{languages}",
        "language": "🌐 Забонро интихоб кун:",
        "too_many": "❌ Файли зеркашишуда хеле калон аст."
    },

    "ru": {
        "welcome": "🎬 Добро пожаловать!\n\n📥 Отправь ссылку TikTok, Instagram или Facebook.",
        "quality": "🎥 Выбери качество:",
        "downloading": "⏳ Загрузка...",
        "done": "✅ Файл отправлен!",
        "error": "❌ Ошибка! Проверь ссылку.",
        "unsupported": "❌ Этот сайт не поддерживается.",
        "large": "❌ Файл превышает лимит Telegram.",
        "choose": "🌐 Выбери язык:",
        "denied": "⛔ Только для администратора.",
        "admin": "🔐 СТАТИСТИКА АДМИНА\n\n👥 Пользователи: {users}\n🟢 Активны сегодня: {active}\n🎬 Загрузки: {downloads}\n\n🌐 Языки:\n{languages}",
        "language": "🌐 Выбери язык:",
        "too_many": "❌ Файл слишком большой."
    },

    "en": {
        "welcome": "🎬 Welcome!\n\n📥 Send a TikTok, Instagram or Facebook link.",
        "quality": "🎥 Choose quality:",
        "downloading": "⏳ Downloading...",
        "done": "✅ File sent!",
        "error": "❌ Error! Check the link.",
        "unsupported": "❌ Unsupported website.",
        "large": "❌ File exceeds Telegram's limit.",
        "choose": "🌐 Choose language:",
        "denied": "⛔ Admin only.",
        "admin": "🔐 ADMIN STATISTICS\n\n👥 Users: {users}\n🟢 Active today: {active}\n🎬 Downloads: {downloads}\n\n🌐 Languages:\n{languages}",
        "language": "🌐 Choose language:",
        "too_many": "❌ File is too large."
    },

    "fa": {
        "welcome": "🎬 خوش آمدید!\n\n📥 لینک TikTok، Instagram یا Facebook را بفرستید.",
        "quality": "🎥 کیفیت را انتخاب کنید:",
        "downloading": "⏳ در حال دانلود...",
        "done": "✅ فایل ارسال شد!",
        "error": "❌ خطا! لینک را بررسی کنید.",
        "unsupported": "❌ سایت پشتیبانی نمی‌شود.",
        "large": "❌ حجم فایل بیشتر از محدودیت تلگرام است.",
        "choose": "🌐 زبان را انتخاب کنید:",
        "denied": "⛔ فقط مدیر.",
        "admin": "🔐 آمار مدیر\n\n👥 کاربران: {users}\n🟢 فعال امروز: {active}\n🎬 دانلودها: {downloads}\n\n🌐 زبان‌ها:\n{languages}",
        "language": "🌐 زبان را انتخاب کنید:",
        "too_many": "❌ فایل بیش از حد بزرگ است."
    },

    "uz": {
        "welcome": "🎬 Xush kelibsiz!\n\n📥 TikTok, Instagram yoki Facebook havolasini yuboring.",
        "quality": "🎥 Sifatni tanlang:",
        "downloading": "⏳ Yuklanmoqda...",
        "done": "✅ Fayl yuborildi!",
        "error": "❌ Xatolik! Havolani tekshiring.",
        "unsupported": "❌ Bu sayt qo‘llab-quvvatlanmaydi.",
        "large": "❌ Fayl Telegram limitidan katta.",
        "choose": "🌐 Tilni tanlang:",
        "denied": "⛔ Faqat admin uchun.",
        "admin": "🔐 ADMIN STATISTIKASI\n\n👥 Foydalanuvchilar: {users}\n🟢 Bugun faol: {active}\n🎬 Yuklashlar: {downloads}\n\n🌐 Tillar:\n{languages}",
        "language": "🌐 Tilni tanlang:",
        "too_many": "❌ Fayl juda katta."
    }
}

LANGUAGES = [
    ("🇹🇯 Тоҷикӣ", "tg"),
    ("🇷🇺 Русский", "ru"),
    ("🇬🇧 English", "en"),
    ("🇮🇷 فارسی", "fa"),
    ("🇺🇿 O‘zbekcha", "uz"),
]

def language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(name, callback_data=f"lang:{code}")]
        for name, code in LANGUAGES
    ])

# ================ START ================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)

    await update.message.reply_text(
        "🌐 Забон / Язык / Language / زبان / Til:",
        reply_markup=language_keyboard()
    )

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEXT[get_language(update.effective_user.id)]["language"],
        reply_markup=language_keyboard()
    )

async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    language = query.data.split(":")[1]
    user_id = query.from_user.id

    register_user(user_id)
    set_language(user_id, language)

    await query.edit_message_text(TEXT[language]["welcome"])

# ================ LINK CHECK ================

def supported_url(url):
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False

    allowed = (
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "fb.watch",
    )

    return any(
        host == domain or host.endswith("." + domain)
        for domain in allowed
    )

# ================ QUALITY BUTTONS ================

def quality_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ 144p", callback_data="quality:144"),
            InlineKeyboardButton("📱 360p", callback_data="quality:360"),
        ],
        [
            InlineKeyboardButton("🎥 480p", callback_data="quality:480"),
            InlineKeyboardButton("🔥 720p HD", callback_data="quality:720"),
        ],
        [
            InlineKeyboardButton("💎 1080p", callback_data="quality:1080"),
            InlineKeyboardButton("🚀 Auto", callback_data="quality:auto"),
        ],
    ])

# ================ RECEIVE LINK ================

async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)

    language = get_language(user_id)
    url = update.message.text.strip()

    match = re.search(r"https?://\S+", url)

    if not match or not supported_url(match.group(0)):
        await update.message.reply_text(TEXT[language]["unsupported"])
        return

    context.user_data["video_url"] = match.group(0)

    await update.message.reply_text(
        TEXT[language]["quality"],
        reply_markup=quality_keyboard()
    )

# ================ DOWNLOAD ENGINE ================

def download_media(url, quality, folder):
    output = str(Path(folder) / "%(id)s.%(ext)s")

    if quality == "auto":
        format_option = "best[ext=mp4]/best"
    else:
        format_option = (
            f"best[height<={quality}][ext=mp4]/"
            f"best[height<={quality}]/best"
        )

    options = {
        "format": format_option,
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_SIZE,
        "merge_output_format": "mp4",
        "writethumbnail": False,
        "ignoreerrors": False,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    files = []

    for path in Path(folder).iterdir():
        if not path.is_file():
            continue

        if path.suffix.lower() in (
            ".mp4", ".mkv", ".webm", ".mov",
            ".jpg", ".jpeg", ".png", ".webp",
        ):
            if path.stat().st_size > 0:
                files.append(path)

    if not files:
        raise Exception("NO_MEDIA")

    files.sort(key=lambda p: p.name)

    for path in files:
        if path.stat().st_size > MAX_SIZE:
            raise Exception("TOO_LARGE")

    title = info.get("title", "Downloaded media")

    return files, title

# ================ SEND PHOTO / VIDEO ================

async def send_media(bot, user_id, files, title):
    for index, path in enumerate(files):
        size = path.stat().st_size

        if size > TELEGRAM_MAX_SIZE:
            raise Exception("TELEGRAM_LIMIT")

        caption = f"🎬 {title[:900]}" if index == 0 else None
        ext = path.suffix.lower()

        with open(path, "rb") as media:
            if ext in (".jpg", ".jpeg", ".png", ".webp") and size <= 10_000_000:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=media,
                    caption=caption
                )

            elif ext in (".mp4", ".mov", ".mkv", ".webm"):
                await bot.send_video(
                    chat_id=user_id,
                    video=media,
                    caption=caption,
                    supports_streaming=True
                )

            else:
                await bot.send_document(
                    chat_id=user_id,
                    document=media,
                    caption=caption
                )

# ================ QUALITY CALLBACK ================

async def download_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    register_user(user_id)

    language = get_language(user_id)
    quality = query.data.split(":")[1]
    url = context.user_data.get("video_url")

    if not url:
        await query.edit_message_text(TEXT[language]["error"])
        return

    await query.edit_message_text(TEXT[language]["downloading"])

    try:
        with tempfile.TemporaryDirectory() as folder:
            files, title = await asyncio.to_thread(
                download_media, url, quality, folder
            )

            await send_media(
                context.bot,
                user_id,
                files,
                title
            )

        add_download(user_id)

        await context.bot.send_message(
            chat_id=user_id,
            text=TEXT[language]["done"]
        )

    except Exception as error:
        print("DOWNLOAD ERROR:", repr(error))

        if "TOO_LARGE" in str(error) or "TELEGRAM_LIMIT" in str(error):
            message = TEXT[language]["large"]
        else:
            message = TEXT[language]["error"]

        await context.bot.send_message(
            chat_id=user_id,
            text=message
        )

# ================ ADMIN STATISTICS ================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)

    language = get_language(user_id)

    if user_id != ADMIN_ID:
        await update.message.reply_text(TEXT[language]["denied"])
        return

    today = datetime.now(timezone.utc).date().isoformat()

    with db() as con:
        users = con.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        active = con.execute(
            "SELECT COUNT(*) FROM users WHERE last_active = ?",
            (today,)
        ).fetchone()[0]

        downloads = con.execute(
            "SELECT COUNT(*) FROM downloads"
        ).fetchone()[0]

        language_rows = con.execute("""
            SELECT language, COUNT(*)
            FROM users
            GROUP BY language
        """).fetchall()

    language_names = dict(LANGUAGES)

    language_stats = "\n".join(
        f"{language_names.get(code, code)}: {count}"
        for code, count in language_rows
    ) or "—"

    await update.message.reply_text(
        TEXT[language]["admin"].format(
            users=users,
            active=active,
            downloads=downloads,
            languages=language_stats
        )
    )

# ================ RUN BOT ================

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_command))

    # Statistics are admin-only
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("stats", admin))

    app.add_handler(
        CallbackQueryHandler(
            choose_language,
            pattern=r"^lang:"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            download_button,
            pattern=r"^quality:"
        )
    )

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
