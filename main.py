
import os
import re
import sqlite3
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

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

# ---------------- SETTINGS ----------------

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949
DB_FILE = "bot_stats.db"
MAX_SIZE = 49 * 1024 * 1024

if not TOKEN:
    raise RuntimeError("BOT_TOKEN дар GitHub Secrets ёфт нашуд!")

# ---------------- DATABASE ----------------

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
            INSERT OR IGNORE INTO users (user_id, language, last_active)
            VALUES (?, 'tg', ?)
        """, (user_id, today))
        con.execute("""
            UPDATE users SET last_active = ? WHERE user_id = ?
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
    now = datetime.now(timezone.utc).isoformat()
    with db() as con:
        con.execute(
            "INSERT INTO downloads (user_id, created_at) VALUES (?, ?)",
            (user_id, now)
        )

# ---------------- LANGUAGES ----------------

TEXT = {
    "tg": {
        "welcome": "🎬 Салом! Ба боти зеркашии видео хуш омадӣ.\n\n📥 Линки TikTok, Instagram ё Facebook-ро фирист.",
        "choose": "🌐 Забонро интихоб кун:",
        "send": "📥 Акнун линкро фирист.",
        "quality": "🎥 Сифати видеоро интихоб кун:",
        "downloading": "⏳ Видео зеркашӣ шуда истодааст...",
        "done": "✅ Видео тайёр шуд!",
        "error": "❌ Хатогӣ! Линкро санҷида, боз фирист.",
        "unsupported": "❌ Ин линк дастгирӣ намешавад. TikTok, Instagram ё Facebook фирист.",
        "large": "❌ Ҳаҷми видео аз 49 МБ зиёд аст.",
        "stats": "📊 ОМОРИ БОТ\n👥 Ҳамагӣ истифодабарандагон: {users}\n🎬 Ҳамагӣ видеоҳои зеркашишуда: {downloads}",
        "admin": "🔐 ОМОРИ АДМИН\n👥 Ҳамагӣ истифодабарандагон: {users}\n🟢 Фаъол имрӯз: {active}\n🎬 Ҳамагӣ зеркашиҳо: {downloads}\n\n🌐 Забонҳо:\n{languages}",
        "denied": "⛔ Ин фармон танҳо барои админ аст.",
        "language": "🌐 Барои иваз кардани забон /language навис."
    },
    "ru": {
        "welcome": "🎬 Привет! Добро пожаловать в бот загрузки видео.\n\n📥 Отправь ссылку TikTok, Instagram или Facebook.",
        "choose": "🌐 Выбери язык:",
        "send": "📥 Теперь отправь ссылку.",
        "quality": "🎥 Выбери качество видео:",
        "downloading": "⏳ Видео загружается...",
        "done": "✅ Видео готово!",
        "error": "❌ Ошибка! Проверь ссылку и попробуй снова.",
        "unsupported": "❌ Поддерживаются TikTok, Instagram и Facebook.",
        "large": "❌ Размер видео больше 49 МБ.",
        "stats": "📊 СТАТИСТИКА\n👥 Всего пользователей: {users}\n🎬 Всего загрузок: {downloads}",
        "admin": "🔐 СТАТИСТИКА АДМИНА\n👥 Всего пользователей: {users}\n🟢 Активны сегодня: {active}\n🎬 Всего загрузок: {downloads}\n\n🌐 Языки:\n{languages}",
        "denied": "⛔ Эта команда только для администратора.",
        "language": "🌐 Для смены языка напиши /language."
    },
    "en": {
        "welcome": "🎬 Welcome to the video downloader bot!\n\n📥 Send a TikTok, Instagram or Facebook link.",
        "choose": "🌐 Choose your language:",
        "send": "📥 Now send a video link.",
        "quality": "🎥 Choose video quality:",
        "downloading": "⏳ Downloading video...",
        "done": "✅ Your video is ready!",
        "error": "❌ Error! Check the link and try again.",
        "unsupported": "❌ Only TikTok, Instagram and Facebook links are supported.",
        "large": "❌ Video is larger than 49 MB.",
        "stats": "📊 BOT STATISTICS\n👥 Total users: {users}\n🎬 Total downloads: {downloads}",
        "admin": "🔐 ADMIN STATISTICS\n👥 Total users: {users}\n🟢 Active today: {active}\n🎬 Total downloads: {downloads}\n\n🌐 Languages:\n{languages}",
        "denied": "⛔ Admin only.",
        "language": "🌐 Type /language to change language."
    },
    "fa": {
        "welcome": "🎬 خوش آمدید!\n\n📥 لینک TikTok، Instagram یا Facebook را بفرستید.",
        "choose": "🌐 زبان را انتخاب کنید:",
        "send": "📥 حالا لینک ویدیو را بفرستید.",
        "quality": "🎥 کیفیت ویدیو را انتخاب کنید:",
        "downloading": "⏳ ویدیو در حال دانلود است...",
        "done": "✅ ویدیو آماده شد!",
        "error": "❌ خطا! لینک را بررسی کنید.",
        "unsupported": "❌ فقط لینک TikTok، Instagram و Facebook پشتیبانی می‌شود.",
        "large": "❌ حجم ویدیو بیشتر از 49 مگابایت است.",
        "stats": "📊 آمار ربات\n👥 کاربران: {users}\n🎬 دانلودها: {downloads}",
        "admin": "🔐 آمار مدیر\n👥 کاربران: {users}\n🟢 فعال امروز: {active}\n🎬 دانلودها: {downloads}\n\n🌐 زبان‌ها:\n{languages}",
        "denied": "⛔ فقط مدیر می‌تواند این دستور را اجرا کند.",
        "language": "🌐 برای تغییر زبان /language را بنویسید."
    },
    "uz": {
        "welcome": "🎬 Video yuklash botiga xush kelibsiz!\n\n📥 TikTok, Instagram yoki Facebook havolasini yuboring.",
        "choose": "🌐 Tilni tanlang:",
        "send": "📥 Endi video havolasini yuboring.",
        "quality": "🎥 Video sifatini tanlang:",
        "downloading": "⏳ Video yuklanmoqda...",
        "done": "✅ Video tayyor!",
        "error": "❌ Xatolik! Havolani tekshiring.",
        "unsupported": "❌ Faqat TikTok, Instagram va Facebook havolalari qo‘llanadi.",
        "large": "❌ Video hajmi 49 MB dan katta.",
        "stats": "📊 BOT STATISTIKASI\n👥 Jami foydalanuvchilar: {users}\n🎬 Jami yuklashlar: {downloads}",
        "admin": "🔐 ADMIN STATISTIKASI\n👥 Foydalanuvchilar: {users}\n🟢 Bugun faol: {active}\n🎬 Yuklashlar: {downloads}\n\n🌐 Tillar:\n{languages}",
        "denied": "⛔ Bu buyruq faqat admin uchun.",
        "language": "🌐 Tilni almashtirish uchun /language yozing."
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

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)

    await update.message.reply_text(
        "🌐 Забон / Язык / Language / زبان / Til:",
        reply_markup=language_keyboard()
    )

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 Забонро интихоб кун:",
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

# ---------------- VIDEO LINK ----------------

def supported_url(url):
    return any(site in url.lower() for site in (
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "fb.watch"
    ))

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

    qualities = [
        [InlineKeyboardButton("144p", callback_data="quality:144")],
        [InlineKeyboardButton("360p", callback_data="quality:360")],
        [InlineKeyboardButton("480p", callback_data="quality:480")],
        [InlineKeyboardButton("720p", callback_data="quality:720")],
        [InlineKeyboardButton("1080p", callback_data="quality:1080")],
        [InlineKeyboardButton("Auto", callback_data="quality:auto")],
    ]

    await update.message.reply_text(
        TEXT[language]["quality"],
        reply_markup=InlineKeyboardMarkup(qualities)
    )

# ---------------- DOWNLOAD ----------------

def download_video(url, quality, folder):
    output = str(Path(folder) / "video.%(ext)s")

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
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    files = list(Path(folder).glob("video.*"))
    if not files:
        raise Exception("Видео ёфт нашуд.")

    video_path = max(files, key=lambda f: f.stat().st_size)

    if video_path.stat().st_size > MAX_SIZE:
        raise Exception("TOO_LARGE")

    return str(video_path), info.get("title", "Video")

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
            video_path, title = await asyncio.to_thread(
                download_video, url, quality, folder
            )

            with open(video_path, "rb") as video:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=video,
                    caption=f"🎬 {title}"
                )

        add_download(user_id)

    except Exception as error:
        if "TOO_LARGE" in str(error):
            message = TEXT[language]["large"]
        else:
            message = TEXT[language]["error"]

        await context.bot.send_message(
            chat_id=user_id,
            text=message
        )

# ---------------- PUBLIC STATISTICS ----------------

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    language = get_language(user_id)

    with db() as con:
        users = con.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        downloads = con.execute(
            "SELECT COUNT(*) FROM downloads"
        ).fetchone()[0]

    await update.message.reply_text(
        TEXT[language]["stats"].format(
            users=users,
            downloads=downloads
        )
    )

# ---------------- ADMIN STATISTICS ----------------

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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

# ---------------- RUN BOT ----------------

def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("admin", admin))

    app.add_handler(
        CallbackQueryHandler(choose_language, pattern=r"^lang:")
    )
    app.add_handler(
        CallbackQueryHandler(download_button, pattern=r"^quality:")
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link)
    )

    print("BOT IS RUNNING...")
    app.run_polling()

if __name__ == "__main__":
    main()
