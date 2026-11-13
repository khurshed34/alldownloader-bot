
import os
import re
import glob
import asyncio
import logging
import tempfile
import shutil
import sqlite3
import requests
import yt_dlp
import instaloader
import base64

from datetime import datetime
from zoneinfo import ZoneInfo
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
from telegram.error import RetryAfter, Forbidden, TelegramError


# =====================================
# SETTINGS
# =====================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6777943949

MAX_SIZE = 49 * 1024 * 1024
DB_NAME = "bot_stats.db"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GITHUB_BRANCH = os.getenv("GITHUB_REF_NAME", "main")
GITHUB_DB_PATH = "bot_stats.db"

TZ = ZoneInfo("Asia/Dushanbe")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN ёфт нашуд.")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


def now():
    return datetime.now(TZ)


# =====================================
# GITHUB DATABASE BACKUP
# =====================================

def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def github_db_url():
    return (
        f"https://api.github.com/repos/"
        f"{GITHUB_REPO}/contents/{GITHUB_DB_PATH}"
    )


def restore_database():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.warning(
            "GitHub backup фаъол нест. База метавонад гум шавад."
        )
        return

    response = requests.get(
        github_db_url(),
        headers=github_headers(),
        params={"ref": GITHUB_BRANCH},
        timeout=30
    )

    if response.status_code == 404:
        logger.info("Базаи нав сохта мешавад.")
        return

    response.raise_for_status()

    data = response.json()
    content = base64.b64decode(data["content"])

    with open(DB_NAME, "wb") as file:
        file.write(content)

    logger.info("База аз GitHub барқарор шуд.")


def backup_database():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    with open(DB_NAME, "rb") as file:
        content = base64.b64encode(file.read()).decode("utf-8")

    url = github_db_url()

    response = requests.get(
        url,
        headers=github_headers(),
        params={"ref": GITHUB_BRANCH},
        timeout=30
    )

    payload = {
        "message": "Update TurboSave statistics",
        "content": content,
        "branch": GITHUB_BRANCH
    }

    if response.status_code == 200:
        payload["sha"] = response.json()["sha"]
    elif response.status_code != 404:
        response.raise_for_status()

    result = requests.put(
        url,
        headers=github_headers(),
        json=payload,
        timeout=60
    )

    result.raise_for_status()

    logger.info("База дар GitHub нигоҳ дошта шуд.")


# =====================================
# DATABASE
# =====================================

def init_db():
    restore_database()

    with sqlite3.connect(DB_NAME) as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                created_at TEXT,
                status TEXT DEFAULT 'success'
            )
        """)

        columns = [
            row[1] for row in
            db.execute("PRAGMA table_info(downloads)").fetchall()
        ]

        if "status" not in columns:
            db.execute("""
                ALTER TABLE downloads
                ADD COLUMN status TEXT DEFAULT 'success'
            """)

    backup_database()


def save_user(user):
    if not user:
        return

    with sqlite3.connect(DB_NAME) as db:

        existing = db.execute(
            "SELECT user_id FROM users WHERE user_id=?",
            (user.id,)
        ).fetchone()

        db.execute("""
            INSERT INTO users
            (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            now().isoformat()
        ))

    if not existing:
        backup_database()


def save_download(user_id, success):
    status = "success" if success else "failed"

    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            INSERT INTO downloads
            (user_id, created_at, status)
            VALUES (?, ?, ?)
        """, (
            user_id,
            now().isoformat(),
            status
        ))

    backup_database()


def get_statistics():
    today = now().date().isoformat()

    with sqlite3.connect(DB_NAME) as db:

        users = db.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        today_users = db.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?",
            (today + "%",)
        ).fetchone()[0]

        total = db.execute(
            "SELECT COUNT(*) FROM downloads"
        ).fetchone()[0]

        success = db.execute("""
            SELECT COUNT(*) FROM downloads
            WHERE status='success'
        """).fetchone()[0]

        failed = db.execute("""
            SELECT COUNT(*) FROM downloads
            WHERE status='failed'
        """).fetchone()[0]

        today_downloads = db.execute("""
            SELECT COUNT(*) FROM downloads
            WHERE created_at LIKE ?
        """, (today + "%",)).fetchone()[0]

    return users, today_users, total, success, failed, today_downloads


def get_users():
    with sqlite3.connect(DB_NAME) as db:
        return db.execute("""
            SELECT user_id, username, first_name
            FROM users
            ORDER BY joined_at DESC
            LIMIT 20
        """).fetchall()


def is_admin(user_id):
    return user_id == ADMIN_ID


# =====================================
# LANGUAGES
# =====================================

TEXTS = {
    "tj": {
        "welcome": "👋 Ба TurboSave Bot хуш омадед!",
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
        "welcome": "👋 Добро пожаловать в TurboSave Bot!",
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
        "welcome": "👋 Welcome to TurboSave Bot!",
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
# HEADERS
# =====================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# =====================================
# DIRECT DOWNLOAD
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
# YT-DLP
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
# INSTAGRAM
# =====================================

def download_instagram(url, folder):
    os.makedirs(folder, exist_ok=True)

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url,
        re.I
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
            post.get_sidecar_nodes(), 1
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
        filename = os.path.join(folder, "instagram_photo.jpg")
        download_file(post.url, filename)
        return [(filename, "photo")]

    filename = os.path.join(folder, "instagram_video.mp4")
    download_file(post.video_url, filename)

    return [(filename, "video")]


# =====================================
# YOUTUBE
# =====================================

def download_youtube(url, folder, quality):
    if not re.search(r"(youtube\.com|youtu\.be)", url, re.I):
        raise ValueError("Пайванди YouTube нодуруст аст.")

    return download_with_ytdlp(url, folder, "youtube", quality)


# =====================================
# TIKTOK
# =====================================

def download_tiktok(url, folder, quality):
    if not re.search(r"tiktok\.com", url, re.I):
        raise ValueError("Пайванди TikTok нодуруст аст.")

    return download_with_ytdlp(url, folder, "tiktok", quality)


# =====================================
# FACEBOOK
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
        logger.warning("Facebook video failed: %s", video_error)

        try:
            return download_facebook_photo(url, folder)

        except Exception as photo_error:
            raise ValueError(
                "Facebook зеркашӣ нашуд.\n"
                "Видео: " + str(video_error)[:250]
                + "\nАкс: " + str(photo_error)[:250]
            )


# =====================================
# PLATFORM DETECTION
# =====================================

def download_media(url, folder, quality):
    url = url.strip()
    domain = urlparse(url).netloc.lower()

    if "instagram.com" in domain:
        return download_instagram(url, folder)

    if "youtube.com" in domain or "youtu.be" in domain:
        return download_youtube(url, folder, quality)

    if "tiktok.com" in domain:
        return download_tiktok(url, folder, quality)

    if any(x in domain for x in [
        "facebook.com", "fb.watch", "fb.com"
    ]):
        return download_facebook(url, folder, quality)

    raise ValueError("Ин платформа дастгирӣ намешавад.")


# =====================================
# START
# =====================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)

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
# LANGUAGE
# =====================================

async def language_callback(update, context):
    query = update.callback_query
    await query.answer()

    save_user(query.from_user)

    lang = query.data.replace("lang_", "")

    if lang not in TEXTS:
        return

    context.user_data["lang"] = lang

    await query.edit_message_text(
        TEXTS[lang]["send_link"]
    )


# =====================================
# ADMIN KEYBOARD
# =====================================

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📊 Омори бот",
            callback_data="admin_stats"
        )],
        [InlineKeyboardButton(
            "👥 Истифодабарандагон",
            callback_data="admin_users"
        )],
        [InlineKeyboardButton(
            "📢 Ирсоли пост",
            callback_data="admin_broadcast"
        )],
    ])


async def admin_panel(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Дастрасӣ манъ аст.")
        return

    await update.message.reply_text(
        "👑 ПАНЕЛИ АДМИН\n\nҚисматро интихоб кун:",
        reply_markup=admin_keyboard()
    )


# =====================================
# ADMIN CALLBACK
# =====================================

async def admin_callback(update, context):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Дастрасӣ манъ аст.")
        return

    if query.data == "admin_stats":

        (
            users,
            today_users,
            total,
            success,
            failed,
            today_downloads
        ) = get_statistics()

        text = (
            "📊 ОМОРИ TURBOSAVE BOT\n\n"
            f"👥 Ҳамаи корбарон: {users}\n"
            f"🆕 Корбарони имрӯз: {today_users}\n\n"
            f"📥 Ҳамаи дархостҳо: {total}\n"
            f"✅ Муваффақ: {success}\n"
            f"❌ Номуваффақ: {failed}\n"
            f"📅 Дархостҳои имрӯз: {today_downloads}"
        )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔄 Навсозӣ",
                    callback_data="admin_stats"
                ),
                InlineKeyboardButton(
                    "🔙 Бозгашт",
                    callback_data="admin_home"
                )
            ]])
        )

    elif query.data == "admin_users":

        users = get_users()
        text = "👥 ОХИРИН ИСТИФОДАБАРАНДАГОН\n\n"

        if not users:
            text += "Ҳоло истифодабаранда нест."

        for index, user in enumerate(users, 1):
            user_id, username, first_name = user

            text += (
                f"{index}. {first_name or 'Беном'}\n"
                f"🆔 {user_id}\n"
                f"👤 @{username or 'username нест'}\n\n"
            )

        await query.edit_message_text(
            text[:4000],
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔙 Бозгашт",
                    callback_data="admin_home"
                )
            ]])
        )

    elif query.data == "admin_broadcast":

        context.user_data["awaiting_broadcast"] = True

        await query.edit_message_text(
            "📢 ПОСТИ ХУДРО ФИРИСТЕД!\n\n"
            "Матн, сурат, видео ё файл фиристед.\n\n"
            "❌ Барои бекор кардан /cancel нависед."
        )

    elif query.data == "admin_home":

        context.user_data["awaiting_broadcast"] = False

        await query.edit_message_text(
            "👑 ПАНЕЛИ АДМИН",
            reply_markup=admin_keyboard()
        )


# =====================================
# BROADCAST
# =====================================

async def broadcast_post(update, context):
    if not is_admin(update.effective_user.id):
        return

    message = update.message

    if not message:
        return

    context.user_data["awaiting_broadcast"] = False

    with sqlite3.connect(DB_NAME) as db:
        users = db.execute(
            "SELECT user_id FROM users"
        ).fetchall()

    success = 0
    failed = 0
    blocked = 0

    status_message = await message.reply_text(
        f"⏳ Ирсол ба {len(users)} корбар оғоз шуд..."
    )

    for index, row in enumerate(users, 1):
        user_id = row[0]

        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            success += 1

        except RetryAfter as error:
            wait_time = error.retry_after
            if hasattr(wait_time, "total_seconds"):
                wait_time = wait_time.total_seconds()

            await asyncio.sleep(float(wait_time) + 1)

            try:
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
                success += 1

            except Forbidden:
                failed += 1
                blocked += 1

            except Exception as retry_error:
                failed += 1
                logger.warning(
                    "Broadcast retry failed for %s: %s",
                    user_id,
                    retry_error
                )

        except Forbidden:
            failed += 1
            blocked += 1

        except TelegramError as error:
            failed += 1
            logger.warning(
                "Broadcast failed for %s: %s",
                user_id,
                error
            )

        except Exception:
            failed += 1
            logger.exception("Broadcast error for %s", user_id)

        if index % 20 == 0:
            try:
                await status_message.edit_text(
                    f"📢 Ирсол идома дорад...\n\n"
                    f"👥 Ҳамагӣ: {len(users)}\n"
                    f"✅ Ирсол шуд: {success}\n"
                    f"❌ Нарафт: {failed}"
                )
            except Exception:
                pass

        await asyncio.sleep(0.05)

    await status_message.edit_text(
        "✅ ИРСОЛИ ПОСТ АНҶОМ ЁФТ!\n\n"
        f"👥 Ҳамагӣ: {len(users)}\n"
        f"✅ Ирсол шуд: {success}\n"
        f"❌ Нарафт: {failed}\n"
        f"🚫 Ботро бастаанд: {blocked}"
    )


async def cancel_broadcast(update, context):
    if not is_admin(update.effective_user.id):
        return

    context.user_data["awaiting_broadcast"] = False

    await update.message.reply_text(
        "❌ Ирсоли пост бекор карда шуд."
    )


# =====================================
# HANDLE MESSAGES
# =====================================

async def handle_message(update, context):
    if not update.message:
        return

    user = update.effective_user
    save_user(user)

    if (
        is_admin(user.id)
        and context.user_data.get("awaiting_broadcast")
    ):
        await broadcast_post(update, context)
        return

    if not update.message.text:
        return

    lang = context.user_data.get("lang")

    if not lang:
        await start(update, context)
        return

    text = update.message.text.strip()

    match = re.search(
        r"https?://[^\s<>]+",
        text,
        re.I
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
        [InlineKeyboardButton(
            "⭐ Best",
            callback_data="quality_best"
        )],
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

            except TelegramError:
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

async def quality_callback(update, context):
    query = update.callback_query
    await query.answer()

    save_user(query.from_user)

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
    recorded = False

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

            try:
                success = await send_media_file(
                    query.message,
                    filename,
                    media_type,
                    lang
                )

                if success:
                    sent += 1

            except Exception as error:
                logger.warning(
                    "File sending failed: %s",
                    error
                )

        save_download(query.from_user.id, sent > 0)
        recorded = True

        await query.message.reply_text(
            TEXTS[lang]["done"]
            + "\n"
            + TEXTS[lang]["sent"].format(sent)
        )

    except Exception as error:
        logger.exception("Download error")

        if not recorded:
            try:
                save_download(query.from_user.id, False)
            except Exception:
                logger.exception("Statistics save failed")

        await query.message.reply_text(
            TEXTS[lang]["failed"].format(str(error)[:500])
        )

    finally:
        shutil.rmtree(folder, ignore_errors=True)
        context.user_data.pop("url", None)


# =====================================
# ERROR HANDLER
# =====================================

async def error_handler(update, context):
    logger.error(
        "Telegram error: %s",
        context.error,
        exc_info=context.error
    )


# =====================================
# MAIN
# =====================================

def main():
    init_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin_panel)
    )

    app.add_handler(
        CommandHandler("cancel", cancel_broadcast)
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
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^admin_"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
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
