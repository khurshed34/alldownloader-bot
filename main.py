import os
import re
import glob
import asyncio
import logging
import tempfile
import shutil
import sqlite3
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin

import requests
import yt_dlp
import instaloader

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.error import RetryAfter, Forbidden, TelegramError, BadRequest


# =========================
# SETTINGS
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6777943949"))
MAX_SIZE = 49 * 1024 * 1024
DB_NAME = "bot_stats.db"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GITHUB_BRANCH = os.getenv("GITHUB_REF_NAME", "main")
GITHUB_DB_PATH = "bot_stats.db"
TZ = ZoneInfo("Asia/Dushanbe")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN ёфт нашуд. Дар GitHub Secrets BOT_TOKEN-ро санҷед.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("turbosave")


def now():
    return datetime.now(TZ)


# =========================
# GITHUB DATABASE BACKUP
# =========================
def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_db_url():
    if not GITHUB_REPO:
        return None
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_DB_PATH}"


def restore_database():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.warning("GitHub DB backup ғайрифаъол аст.")
        return

    try:
        response = requests.get(
            github_db_url(),
            headers=github_headers(),
            params={"ref": GITHUB_BRANCH},
            timeout=25,
        )
        if response.status_code == 404:
            logger.info("DB дар GitHub нест; DB-и нав сохта мешавад.")
            return
        response.raise_for_status()
        payload = response.json()
        raw = base64.b64decode(payload["content"])
        with open(DB_NAME, "wb") as f:
            f.write(raw)
        logger.info("DB аз GitHub барқарор шуд.")
    except Exception:
        logger.exception("Хатои барқарор кардани DB аз GitHub.")


def backup_database():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    try:
        with open(DB_NAME, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")

        url = github_db_url()
        current = requests.get(
            url,
            headers=github_headers(),
            params={"ref": GITHUB_BRANCH},
            timeout=25,
        )

        body = {
            "message": "Update TurboSave bot database",
            "content": encoded,
            "branch": GITHUB_BRANCH,
        }
        if current.status_code == 200:
            body["sha"] = current.json()["sha"]
        elif current.status_code != 404:
            current.raise_for_status()

        result = requests.put(
            url,
            headers=github_headers(),
            json=body,
            timeout=45,
        )
        result.raise_for_status()
        logger.info("DB ба GitHub backup шуд.")
    except Exception:
        logger.exception("GitHub DB backup ноком шуд.")


# =========================
# DATABASE
# =========================
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
        cols = {
            row[1] for row in db.execute("PRAGMA table_info(downloads)").fetchall()
        }
        if "status" not in cols:
            db.execute("ALTER TABLE downloads ADD COLUMN status TEXT DEFAULT 'success'")
    backup_database()


def save_user(user):
    if user is None:
        return
    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            INSERT INTO users (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            now().isoformat(),
        ))


def save_download(user_id, success):
    with sqlite3.connect(DB_NAME) as db:
        db.execute("""
            INSERT INTO downloads (user_id, created_at, status)
            VALUES (?, ?, ?)
        """, (
            user_id,
            now().isoformat(),
            "success" if success else "failed",
        ))


def get_statistics():
    today = now().date().isoformat()
    with sqlite3.connect(DB_NAME) as db:
        users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today_users = db.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (today + "%",)
        ).fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        success = db.execute(
            "SELECT COUNT(*) FROM downloads WHERE status='success'"
        ).fetchone()[0]
        failed = db.execute(
            "SELECT COUNT(*) FROM downloads WHERE status='failed'"
        ).fetchone()[0]
        today_downloads = db.execute(
            "SELECT COUNT(*) FROM downloads WHERE created_at LIKE ?", (today + "%",)
        ).fetchone()[0]
    return users, today_users, total, success, failed, today_downloads


def get_users():
    with sqlite3.connect(DB_NAME) as db:
        return db.execute("""
            SELECT user_id, username, first_name
            FROM users ORDER BY joined_at DESC LIMIT 30
        """).fetchall()


def is_admin(user_id):
    return user_id == ADMIN_ID


# =========================
# TEXTS
# =========================
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
    },
    "ru": {
        "welcome": "👋 Добро пожаловать в TurboSave Bot!",
        "send_link": "🔗 Отправьте ссылку на видео или фото.",
        "quality": "🎬 Выберите качество видео:",
        "downloading": "⏳ Загрузка началась...",
        "sending": "📤 Отправка файла...",
        "done": "✅ Готово!",
        "failed": "❌ Ошибка загрузки:\n{}",
        "invalid": "❌ Отправьте правильную ссылку.",
        "large": "❌ Размер файла превышает 49 MB.",
        "unsupported": "❌ Эта платформа не поддерживается.",
        "sent": "📤 Отправлено файлов: {}",
    },
    "en": {
        "welcome": "👋 Welcome to TurboSave Bot!",
        "send_link": "🔗 Send a video or photo link.",
        "quality": "🎬 Choose video quality:",
        "downloading": "⏳ Download started...",
        "sending": "📤 Sending file...",
        "done": "✅ Completed!",
        "failed": "❌ Download failed:\n{}",
        "invalid": "❌ Please send a valid link.",
        "large": "❌ File size exceeds 49 MB.",
        "unsupported": "❌ This platform is not supported.",
        "sent": "📤 Files sent: {}",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# =========================
# DOWNLOAD HELPERS
# =========================
def download_file(url, filename):
    with requests.get(url, headers=HEADERS, stream=True, timeout=(20, 90)) as response:
        response.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in response.iter_content(1024 * 512):
                if chunk:
                    f.write(chunk)
    if not os.path.isfile(filename) or os.path.getsize(filename) == 0:
        raise ValueError("Файл холӣ аст ё зеркашӣ нашуд.")


def find_downloaded_file(folder, prefix):
    candidates = [
        path for path in glob.glob(os.path.join(folder, prefix + "*"))
        if os.path.isfile(path)
        and not path.endswith((".part", ".ytdl", ".json"))
    ]
    if not candidates:
        raise ValueError("Файли зеркашишуда ёфт нашуд.")
    return max(candidates, key=os.path.getsize)


def download_with_ytdlp(url, folder, prefix, quality="best"):
    os.makedirs(folder, exist_ok=True)
    output = os.path.join(folder, prefix + "_%(id)s.%(ext)s")

    if quality == "best":
        fmt = "best[ext=mp4]/best"
    else:
        fmt = (
            f"bestvideo[height<={quality}]+bestaudio/"
            f"best[height<={quality}]/best"
        )

    options = {
        "format": fmt,
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
    return [(find_downloaded_file(folder, prefix), "video")]


def download_instagram(url, folder):
    os.makedirs(folder, exist_ok=True)
    shortcode_match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url, re.I,
    )
    if not shortcode_match:
        raise ValueError("Пайванди Instagram нодуруст аст.")

    shortcode = shortcode_match.group(1)
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )
    post = instaloader.Post.from_shortcode(loader.context, shortcode)
    results = []

    if post.typename == "GraphSidecar":
        for index, node in enumerate(post.get_sidecar_nodes(), 1):
            if node.is_video:
                media_url, ext, kind = node.video_url, ".mp4", "video"
            else:
                media_url, ext, kind = node.display_url, ".jpg", "photo"
            filename = os.path.join(folder, f"instagram_{index}{ext}")
            download_file(media_url, filename)
            results.append((filename, kind))
        return results

    if post.is_video:
        filename = os.path.join(folder, "instagram_video.mp4")
        download_file(post.video_url, filename)
        return [(filename, "video")]

    filename = os.path.join(folder, "instagram_photo.jpg")
    download_file(post.url, filename)
    return [(filename, "photo")]


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
    response = session.get(url, allow_redirects=True, timeout=60)
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
        image_url, stream=True, timeout=90,
        headers={"Referer": response.url},
    )
    image_response.raise_for_status()
    content_type = image_response.headers.get("Content-Type", "").lower()
    if not content_type.startswith("image/"):
        raise ValueError("Файли акс дастрас нест.")

    ext = ".jpg"
    if "png" in content_type:
        ext = ".png"
    elif "webp" in content_type:
        ext = ".webp"

    filename = os.path.join(folder, "facebook_photo" + ext)
    with open(filename, "wb") as f:
        for chunk in image_response.iter_content(1024 * 512):
            if chunk:
                f.write(chunk)
    return [(filename, "photo")]


def download_facebook(url, folder, quality):
    try:
        return download_with_ytdlp(url, folder, "facebook", quality)
    except Exception as video_error:
        logger.warning("Facebook video download failed: %s", video_error)
        try:
            return download_facebook_photo(url, folder)
        except Exception as photo_error:
            raise ValueError(
                "Facebook зеркашӣ нашуд. Видео: "
                + str(video_error)[:200]
                + " | Акс: " + str(photo_error)[:200]
            )


def download_media(url, folder, quality):
    parsed = urlparse(url)
    domain = (parsed.netloc or "").lower().split(":")[0]
    if not parsed.scheme.startswith("http"):
        raise ValueError("Пайванд бояд http ё https бошад.")

    if domain.endswith("instagram.com"):
        return download_instagram(url, folder)
    if domain.endswith("youtube.com") or domain == "youtu.be":
        return download_with_ytdlp(url, folder, "youtube", quality)
    if domain.endswith("tiktok.com"):
        return download_with_ytdlp(url, folder, "tiktok", quality)
    if domain.endswith("facebook.com") or domain in ("fb.watch", "fb.com"):
        return download_facebook(url, folder, quality)
    raise ValueError("Ин платформа дастгирӣ намешавад.")


# =========================
# BOT COMMANDS / LANGUAGE
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.to_thread(save_user, update.effective_user)
    keyboard = [
        [
            InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang_tj"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        ],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ]
    await update.effective_message.reply_text(
        "🌍 Забон / Язык / Language",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await asyncio.to_thread(save_user, query.from_user)
    lang = query.data.removeprefix("lang_")
    if lang not in TEXTS:
        return
    context.user_data["lang"] = lang
    await query.edit_message_text(TEXTS[lang]["send_link"])


def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Омори бот", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Истифодабарандагон", callback_data="admin_users")],
        [InlineKeyboardButton("📢 Ирсоли пост", callback_data="admin_broadcast")],
    ])


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Дастрасӣ манъ аст.")
        return
    await update.effective_message.reply_text(
        "👑 ПАНЕЛИ АДМИН\n\nҚисматро интихоб кун:",
        reply_markup=admin_keyboard(),
    )


async def safe_edit(query, text, reply_markup=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as error:
        if "Message is not modified" not in str(error):
            raise


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await safe_edit(query, "⛔ Дастрасӣ манъ аст.")
        return

    if query.data == "admin_stats":
        users, today_users, total, success, failed, today_downloads = await asyncio.to_thread(get_statistics)
        text = (
            "📊 ОМОРИ TURBOSAVE BOT\n\n"
            f"👥 Ҳамаи корбарон: {users}\n"
            f"🆕 Корбарони имрӯз: {today_users}\n\n"
            f"📥 Ҳамаи дархостҳо: {total}\n"
            f"✅ Муваффақ: {success}\n"
            f"❌ Номуваффақ: {failed}\n"
            f"📅 Дархостҳои имрӯз: {today_downloads}"
        )
        await safe_edit(query, text, InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Навсозӣ", callback_data="admin_stats"),
            InlineKeyboardButton("🔙 Бозгашт", callback_data="admin_home"),
        ]]))

    elif query.data == "admin_users":
        users = await asyncio.to_thread(get_users)
        lines = ["👥 ОХИРИН ИСТИФОДАБАРАНДАГОН\n"]
        for index, (user_id, username, first_name) in enumerate(users, 1):
            lines.append(
                f"{index}. {first_name or 'Беном'}\n"
                f"🆔 {user_id}\n"
                f"👤 @{username or 'username нест'}\n"
            )
        if not users:
            lines.append("Ҳоло истифодабаранда нест.")
        await safe_edit(query, "\n".join(lines)[:4000],
                        InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Бозгашт", callback_data="admin_home")
                        ]]))

    elif query.data == "admin_broadcast":
        context.user_data["awaiting_broadcast"] = True
        await safe_edit(
            query,
            "📢 ПОСТИ ХУДРО ФИРИСТЕД!\n\n"
            "Матн, сурат, видео ё файл фиристед.\n"
            "❌ Барои бекор кардан /cancel нависед.",
        )

    elif query.data == "admin_home":
        context.user_data["awaiting_broadcast"] = False
        await safe_edit(query, "👑 ПАНЕЛИ АДМИН", admin_keyboard())


# =========================
# BROADCAST
# =========================
async def broadcast_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    message = update.effective_message
    users = await asyncio.to_thread(
        lambda: sqlite3.connect(DB_NAME).execute(
            "SELECT user_id FROM users"
        ).fetchall()
    )
    context.user_data["awaiting_broadcast"] = False
    status = await message.reply_text(
        f"⏳ Ирсол ба {len(users)} корбар оғоз шуд..."
    )
    sent = failed = blocked = 0

    for index, (user_id,) in enumerate(users, 1):
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
            sent += 1
        except RetryAfter as error:
            delay = error.retry_after
            if hasattr(delay, "total_seconds"):
                delay = delay.total_seconds()
            await asyncio.sleep(float(delay) + 1)
            try:
                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id,
                )
                sent += 1
            except Forbidden:
                failed += 1
                blocked += 1
            except TelegramError as retry_error:
                failed += 1
                logger.warning("Broadcast retry failed for %s: %s", user_id, retry_error)
        except Forbidden:
            failed += 1
            blocked += 1
        except TelegramError as error:
            failed += 1
            logger.warning("Broadcast failed for %s: %s", user_id, error)

        if index % 20 == 0:
            try:
                await status.edit_text(
                    f"📢 Ирсол идома дорад...\n\n"
                    f"👥 Ҳамагӣ: {len(users)}\n"
                    f"✅ Ирсол шуд: {sent}\n"
                    f"❌ Нарафт: {failed}"
                )
            except TelegramError:
                pass
        await asyncio.sleep(0.05)

    await status.edit_text(
        "✅ ИРСОЛИ ПОСТ АНҶОМ ЁФТ!\n\n"
        f"👥 Ҳамагӣ: {len(users)}\n"
        f"✅ Ирсол шуд: {sent}\n"
        f"❌ Нарафт: {failed}\n"
        f"🚫 Ботро бастаанд: {blocked}"
    )


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    context.user_data["awaiting_broadcast"] = False
    await update.effective_message.reply_text("❌ Ирсоли пост бекор карда шуд.")


# =========================
# INCOMING MESSAGES
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    await asyncio.to_thread(save_user, user)

    if is_admin(user.id) and context.user_data.get("awaiting_broadcast"):
        await broadcast_post(update, context)
        return

    if not message.text:
        lang = context.user_data.get("lang", "tj")
        await message.reply_text(TEXTS[lang]["invalid"])
        return

    lang = context.user_data.get("lang")
    if lang not in TEXTS:
        await start(update, context)
        return

    match = re.search(r"https?://[^\s<>]+", message.text, re.I)
    if not match:
        await message.reply_text(TEXTS[lang]["invalid"])
        return

    url = match.group(0).rstrip(".,!?;:)]}")
    domain = (urlparse(url).netloc or "").lower().split(":")[0]
    supported = (
        domain.endswith("instagram.com")
        or domain.endswith("youtube.com")
        or domain == "youtu.be"
        or domain.endswith("tiktok.com")
        or domain.endswith("facebook.com")
        or domain in ("fb.watch", "fb.com")
    )
    if not supported:
        await message.reply_text(TEXTS[lang]["unsupported"])
        return

    context.user_data["url"] = url
    keyboard = [
        [InlineKeyboardButton("⭐ Best", callback_data="quality_best")],
        [
            InlineKeyboardButton("1080p", callback_data="quality_1080"),
            InlineKeyboardButton("720p", callback_data="quality_720"),
        ],
        [
            InlineKeyboardButton("480p", callback_data="quality_480"),
            InlineKeyboardButton("360p", callback_data="quality_360"),
        ],
    ]
    await message.reply_text(
        TEXTS[lang]["quality"],
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# SEND DOWNLOADED MEDIA
# =========================
async def send_media_file(message, filename, media_type, lang):
    if not os.path.isfile(filename):
        raise FileNotFoundError("Файл ёфт нашуд.")
    size = os.path.getsize(filename)
    if size <= 0:
        raise ValueError("Файл холӣ аст.")
    if size > MAX_SIZE:
        await message.reply_text(TEXTS[lang]["large"])
        return False

    with open(filename, "rb") as media:
        if media_type == "video":
            await message.reply_video(
                video=media,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
            )
        else:
            try:
                await message.reply_photo(
                    photo=media,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                )
            except TelegramError:
                media.seek(0)
                await message.reply_document(
                    document=media,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                )
    return True


# =========================
# QUALITY CALLBACK
# =========================
async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await asyncio.to_thread(save_user, query.from_user)

    lang = context.user_data.get("lang", "tj")
    url = context.user_data.get("url")
    if not url:
        await query.message.reply_text(TEXTS[lang]["invalid"])
        return

    quality = query.data.removeprefix("quality_")
    if quality not in ("best", "1080", "720", "480", "360"):
        return

    try:
        await query.edit_message_text(TEXTS[lang]["downloading"])
    except TelegramError:
        pass

    folder = tempfile.mkdtemp(prefix="turbosave_")
    success = False
    try:
        results = await asyncio.to_thread(download_media, url, folder, quality)
        if not results:
            raise ValueError("Ягон файл зеркашӣ нашуд.")

        await query.message.reply_text(TEXTS[lang]["sending"])
        sent = 0
        errors = []

        for filename, media_type in results:
            try:
                if await send_media_file(query.message, filename, media_type, lang):
                    sent += 1
            except Exception as error:
                logger.exception("Sending media failed")
                errors.append(str(error)[:150])

        success = sent > 0
        if not success:
            raise ValueError("Файл зеркашӣ шуд, аммо Telegram онро нафиристод. " + "; ".join(errors))

        await query.message.reply_text(
            TEXTS[lang]["done"] + "\n" + TEXTS[lang]["sent"].format(sent)
        )

    except Exception as error:
        logger.exception("Download/Send operation failed")
        await query.message.reply_text(
            TEXTS[lang]["failed"].format(str(error)[:700])
        )
    finally:
        try:
            await asyncio.to_thread(save_download, query.from_user.id, success)
            await asyncio.to_thread(backup_database)
        except Exception:
            logger.exception("Saving download statistics failed")
        shutil.rmtree(folder, ignore_errors=True)
        context.user_data.pop("url", None)


# =========================
# ERROR HANDLER
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(
        "Unhandled Telegram update error",
        exc_info=(type(context.error), context.error, context.error.__traceback__)
        if context.error else None,
    )


# =========================
# MAIN
# =========================
def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))

    app.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern=r"^quality_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin_"))

    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, handle_message)
    )
    app.add_error_handler(error_handler)

    logger.info("TurboSave Bot is starting. Polling is enabled.")
    # run_polling худаш webhook-и пешинаро нест мекунад.
    # Ду нусхаи ботро бо як BOT_TOKEN ҳамзамон ба кор наандозед.
    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
        poll_interval=1.0,
        timeout=30,
    )


if __name__ == "__main__":
    main()
