
import os
import uuid
import tempfile
import ipaddress
from urllib.parse import urlparse

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp


# =====================================
# TURBOSAVE SETTINGS
# =====================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not found")

bot = telebot.TeleBot(TOKEN)

# Telegram upload safety limit
MAX_SIZE = 45 * 1024 * 1024

jobs = {}

ALLOWED_DOMAINS = (
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
    "pinterest.com",
)

VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".mov", ".webm", ".avi"
)

IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".webp"
)


# =====================================
# URL VALIDATION
# =====================================

def valid_url(url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname

        if parsed.scheme not in ("http", "https"):
            return False

        if not host or parsed.username or parsed.password:
            return False

        host = host.lower()

        allowed = any(
            host == domain or host.endswith("." + domain)
            for domain in ALLOWED_DOMAINS
        )

        if not allowed:
            return False

        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                return False
        except ValueError:
            pass

        return True

    except Exception:
        return False


def get_platform(url):
    host = (urlparse(url).hostname or "").lower()

    platforms = {
        "instagram.com": "Instagram",
        "tiktok.com": "TikTok",
        "facebook.com": "Facebook",
        "fb.watch": "Facebook",
        "twitter.com": "X",
        "x.com": "X",
        "pinterest.com": "Pinterest",
    }

    for domain, name in platforms.items():
        if host == domain or host.endswith("." + domain):
            return name

    return "Дигар"


# =====================================
# KEYBOARDS
# =====================================

def mode_keyboard(job_id):
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton(
            "🎬 Видео",
            callback_data=f"v|video|{job_id}"
        ),
        InlineKeyboardButton(
            "🎵 Мусиқӣ MP3",
            callback_data=f"a|mp3|{job_id}"
        )
    )

    return keyboard


def video_quality_keyboard(job_id):
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton(
            "360p",
            callback_data=f"q|360|{job_id}"
        ),
        InlineKeyboardButton(
            "720p",
            callback_data=f"q|720|{job_id}"
        ),
        InlineKeyboardButton(
            "1080p",
            callback_data=f"q|1080|{job_id}"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "⭐ Баландтарин сифат",
            callback_data=f"q|best|{job_id}"
        )
    )

    return keyboard


# =====================================
# START
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "📥 Оғози зеркашӣ",
            callback_data="help"
        )
    )

    bot.send_message(
        message.chat.id,
        "👋 Хуш омадед ба TurboSave!\n\n"
        "📸 Instagram — акс ва видео\n"
        "🎬 TikTok — видео\n"
        "📥 Facebook — маводи дастрас\n"
        "🐦 X — видео\n"
        "📌 Pinterest — акс ва видео\n\n"
        "🔗 Ссылкаи маводро фиристед.\n\n"
        "🎬 Видео ё 🎵 MP3-ро худатон интихоб мекунед.",
        reply_markup=keyboard
    )


# =====================================
# HELP
# =====================================

@bot.message_handler(commands=["help"])
def help_command(message):
    bot.reply_to(
        message,
        "📌 Тарзи истифода:\n\n"
        "1. Ссылка фиристед.\n"
        "2. Видео ё MP3-ро интихоб кунед.\n"
        "3. Барои видео сифатро интихоб кунед.\n"
        "4. Файлро қабул кунед.\n\n"
        "📦 Ҳадди файл: 45 MB\n"
        "⚠️ Танҳо маводи иҷозатдодашударо зеркашӣ кунед."
    )


@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_button(call):
    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,
        "🔗 Лутфан ссылкаи видео ё аксро фиристед."
    )


# =====================================
# RECEIVE LINK
# =====================================

@bot.message_handler(
    content_types=["text"],
    func=lambda m: bool(m.text) and not m.text.startswith("/")
)
def receive_link(message):
    url = message.text.strip()

    if not valid_url(url):
        bot.reply_to(
            message,
            "❌ Ссылка дуруст нест ё сайт дастгирӣ намешавад.\n\n"
            "YouTube дар ин версия дастгирӣ намешавад."
        )
        return

    platform = get_platform(url)
    job_id = uuid.uuid4().hex[:12]

    jobs[job_id] = {
        "url": url,
        "user": message.from_user.id
    }

    bot.reply_to(
        message,
        f"✅ Ссылка қабул шуд!\n\n"
        f"🌐 Платформа: {platform}\n\n"
        f"📥 Чиро зеркашӣ мекунед?",
        reply_markup=mode_keyboard(job_id)
    )


# =====================================
# FIND FILE
# =====================================

def find_file(folder, mode):
    candidates = []

    for root, dirs, files in os.walk(folder):
        for filename in files:
            path = os.path.join(root, filename)
            lower = filename.lower()

            if lower.endswith((
                ".part", ".ytdl", ".json",
                ".description", ".vtt", ".srt"
            )):
                continue

            if not os.path.isfile(path):
                continue

            if os.path.getsize(path) == 0:
                continue

            candidates.append(path)

    if mode == "mp3":
        mp3_files = [
            p for p in candidates
            if p.lower().endswith(".mp3")
        ]

        if mp3_files:
            return max(mp3_files, key=os.path.getsize)

        raise ValueError("MP3 сохта нашуд. FFmpeg-ро санҷед.")

    videos = [
        p for p in candidates
        if p.lower().endswith(VIDEO_EXTENSIONS)
    ]

    if videos:
        mp4_files = [
            p for p in videos
            if p.lower().endswith(".mp4")
        ]

        if mp4_files:
            return max(mp4_files, key=os.path.getsize)

        return max(videos, key=os.path.getsize)

    images = [
        p for p in candidates
        if p.lower().endswith(IMAGE_EXTENSIONS)
    ]

    if images:
        return max(images, key=os.path.getsize)

    raise ValueError("Файли омодашуда ёфт нашуд.")


# =====================================
# DOWNLOAD ENGINE
# =====================================

def download_media(url, quality, folder):

    output_template = os.path.join(
        folder,
        "%(id)s.%(ext)s"
    )

    if quality == "mp3":

        options = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "max_filesize": MAX_SIZE,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ],
        }

    else:

        if quality == "best":
            fmt = "bestvideo+bestaudio/best"
        else:
            fmt = (
                f"bestvideo[height<={quality}]+bestaudio/"
                f"best[height<={quality}]/best"
            )

        options = {
            "format": fmt,
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "max_filesize": MAX_SIZE,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "quiet": True,
            "no_warnings": True,
        }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

        if not info:
            raise ValueError("Мавод дастрас нест.")

    path = find_file(folder, quality)

    size = os.path.getsize(path)

    if size > MAX_SIZE:
        raise ValueError("Файл аз 45 MB калон аст.")

    return path


# =====================================
# ERROR MESSAGES
# =====================================

def friendly_error(error):
    message = str(error).lower()

    if (
        "instagram:story" in message
        or "you need to log in to access this content" in message
    ):
        return (
            "🔒 Instagram барои дидани ин Story иҷозат талаб мекунад.\n\n"
            "📌 Видео ё Reels-и дастраси оммавиро санҷед."
        )

    if (
        "private" in message
        or "login required" in message
        or "authentication" in message
        or "cookies" in message
    ):
        return (
            "🔒 Ин мавод дастрас нест ё иҷозат талаб мекунад."
        )

    if "ffmpeg" in message or "ffprobe" in message:
        return (
            "❌ Дар коркарди файл мушкили FFmpeg пайдо шуд."
        )

    if (
        "too large" in message
        or "max_filesize" in message
        or "file is larger" in message
    ):
        return (
            "📦 Файл аз 45 MB калон аст.\n"
            "Сифати пасттарро интихоб кунед."
        )

    if (
        "unsupported url" in message
        or "no suitable extractor" in message
    ):
        return "❌ Ин ссылка дастгирӣ намешавад."

    if (
        "unable to download" in message
        or "http error" in message
    ):
        return (
            "🌐 Сайт ҷавоб намедиҳад ё файл дастрас нест.\n"
            "Баъдтар аз нав санҷед."
        )

    return (
        "❌ Зеркашӣ иҷро нашуд.\n"
        "Сайт, формат ё файл метавонад дастрас набошад."
    )


# =====================================
# CALLBACK HANDLER
# =====================================

@bot.callback_query_handler(
    func=lambda call: (
        call.data.startswith("v|")
        or call.data.startswith("q|")
        or call.data.startswith("a|")
    )
)
def download_callback(call):

    status = None
    job_id = None
    action = None

    try:
        parts = call.data.split("|")

        if len(parts) != 3:
            bot.answer_callback_query(
                call.id,
                "Дархост нодуруст аст."
            )
            return

        action, choice, job_id = parts

        job = jobs.get(job_id)

        if not job:
            bot.answer_callback_query(
                call.id,
                "Ссылка кӯҳна шудааст. Аз нав фиристед."
            )
            return

        if job["user"] != call.from_user.id:
            bot.answer_callback_query(
                call.id,
                "Ин тугма барои шумо нест."
            )
            return

        # User chooses video
        if action == "v":

            if choice != "video":
                bot.answer_callback_query(
                    call.id,
                    "Интихоб нодуруст аст."
                )
                return

            bot.answer_callback_query(
                call.id,
                "🎬 Сифати видеоро интихоб кунед."
            )

            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=video_quality_keyboard(job_id)
            )

            return

        # Audio choice
        if action == "a" and choice != "mp3":
            bot.answer_callback_query(
                call.id,
                "Формати аудио нодуруст аст."
            )
            return

        # Video quality choice
        if action == "q" and choice not in (
            "360", "720", "1080", "best"
        ):
            bot.answer_callback_query(
                call.id,
                "Сифат нодуруст аст."
            )
            return

        bot.answer_callback_query(
            call.id,
            "⏳ Зеркашӣ оғоз шуд..."
        )

        status = bot.send_message(
            call.message.chat.id,
            "⏳ Лутфан интизор шавед...\n"
            "TurboSave файлро омода мекунад."
        )

        mode = "mp3" if action == "a" else choice

        with tempfile.TemporaryDirectory() as folder:

            path = download_media(
                job["url"],
                mode,
                folder
            )

            ext = os.path.splitext(path)[1].lower()

            with open(path, "rb") as media:

                if mode == "mp3":
                    bot.send_audio(
                        call.message.chat.id,
                        media,
                        title="TurboSave MP3",
                        caption="🎵 TurboSave | MP3"
                    )

                elif ext in IMAGE_EXTENSIONS:
                    bot.send_photo(
                        call.message.chat.id,
                        media,
                        caption="📸 TurboSave"
                    )

                elif ext == ".mp4":
                    bot.send_video(
                        call.message.chat.id,
                        media,
                        caption="✅ TurboSave"
                    )

                else:
                    bot.send_document(
                        call.message.chat.id,
                        media,
                        caption="✅ TurboSave"
                    )

        bot.send_message(
            call.message.chat.id,
            "✅ Зеркашӣ анҷом ёфт!"
        )

    except Exception as error:

        print("DOWNLOAD ERROR:", repr(error))

        try:
            bot.send_message(
                call.message.chat.id,
                friendly_error(error)
            )
        except Exception as send_error:
            print("TELEGRAM SEND ERROR:", repr(send_error))

    finally:

        if job_id and action in ("q", "a"):
            jobs.pop(job_id, None)

        if status:
            try:
                bot.delete_message(
                    status.chat.id,
                    status.message_id
                )
            except Exception:
                pass


# =====================================
# START BOT
# =====================================

print("TurboSave is running...")
print("yt-dlp version:", yt_dlp.version.__version__)

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
