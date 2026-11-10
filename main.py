
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

MAX_SIZE = 45 * 1024 * 1024
jobs = {}

ALLOWED_DOMAINS = (
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
    "pinterest.com",
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

        if not host:
            return False

        host = host.lower()

        if not any(
            host == domain or host.endswith("." + domain)
            for domain in ALLOWED_DOMAINS
        ):
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
    host = urlparse(url).hostname.lower()

    platforms = {
        "instagram.com": "Instagram",
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
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

def quality_keyboard(job_id):

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
        ),
    )

    keyboard.add(
        InlineKeyboardButton(
            "⭐ Баландтарин сифат",
            callback_data=f"q|best|{job_id}"
        )
    )

    keyboard.add(
        InlineKeyboardButton(
            "🎵 MP3 320 kbps",
            callback_data=f"a|mp3|{job_id}"
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
        "🎵 YouTube — MP3\n"
        "🎬 YouTube — видео\n"
        "🎵 TikTok — видео\n\n"
        "🔗 Ссылкаи маводи иҷозатдодашударо фиристед.",
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
        "2. Сифати видеоро интихоб кунед.\n"
        "3. Барои аудио MP3-ро пахш кунед.\n"
        "4. Файлро қабул кунед.\n\n"
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
    func=lambda m: not m.text.startswith("/")
)
def receive_link(message):

    url = message.text.strip()

    if not valid_url(url):
        bot.reply_to(
            message,
            "❌ Ссылка дуруст нест ё сайт дастгирӣ намешавад."
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
        f"📥 Сифати дилхоҳро интихоб кунед:",
        reply_markup=quality_keyboard(job_id)
    )


# =====================================
# FIND DOWNLOADED FILE
# =====================================

def find_file(folder, info, mode):

    candidates = []

    for root, dirs, files in os.walk(folder):
        for filename in files:

            if filename.endswith(".part"):
                continue

            path = os.path.join(root, filename)

            if os.path.isfile(path):
                candidates.append(path)

    if not candidates:
        raise ValueError("Файл сохта нашуд")

    if mode == "mp3":
        mp3_files = [
            p for p in candidates
            if p.lower().endswith(".mp3")
        ]

        if mp3_files:
            return mp3_files[0]

        raise ValueError("MP3 сохта нашуд. FFmpeg-ро санҷед.")

    final_files = [
        p for p in candidates
        if not p.lower().endswith((".webm", ".m4a", ".f4v"))
    ]

    if final_files:
        candidates = final_files

    return max(candidates, key=os.path.getsize)


# =====================================
# DOWNLOAD ENGINE
# =====================================

def download_media(url, quality, folder):

    if quality == "mp3":

        options = {
            "format": "bestaudio/best",

            "outtmpl": os.path.join(
                folder, "%(id)s.%(ext)s"
            ),

            "noplaylist": True,
            "max_filesize": MAX_SIZE,
            "socket_timeout": 30,
            "retries": 3,
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

            "outtmpl": os.path.join(
                folder, "%(id)s.%(ext)s"
            ),

            "merge_output_format": "mp4",
            "noplaylist": True,
            "max_filesize": MAX_SIZE,
            "socket_timeout": 30,
            "retries": 3,
            "quiet": True,
            "no_warnings": True,
        }

    with yt_dlp.YoutubeDL(options) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        if not info:
            raise ValueError("Мавод дастрас нест")

    path = find_file(folder, info, quality)

    size = os.path.getsize(path)

    if size > MAX_SIZE:
        raise ValueError("Файл аз 45 MB калон аст")

    return path


# =====================================
# CALLBACK HANDLER
# =====================================

@bot.callback_query_handler(
    func=lambda call: (
        call.data.startswith("q|")
        or call.data.startswith("a|")
    )
)
def download_callback(call):

    status = None
    job_id = None

    try:

        parts = call.data.split("|")

        action = parts[0]
        quality = parts[1]
        job_id = parts[2]

        job = jobs.get(job_id)

        if not job:
            bot.answer_callback_query(
                call.id,
                "Ссылка кӯҳна шудааст."
            )
            return

        if job["user"] != call.from_user.id:
            bot.answer_callback_query(
                call.id,
                "Ин тугма барои шумо нест."
            )
            return

        if action == "a" and quality != "mp3":
            raise ValueError("Ин формати аудио дастгирӣ намешавад")

        bot.answer_callback_query(
            call.id,
            "⏳ Зеркашӣ оғоз шуд..."
        )

        status = bot.send_message(
            call.message.chat.id,
            "⏳ Лутфан интизор шавед...\n"
            "TurboSave файлро омода мекунад."
        )

        mode = "mp3" if action == "a" else quality

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

                elif ext in (".jpg", ".jpeg", ".png", ".webp"):

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

        bot.delete_message(
            status.chat.id,
            status.message_id
        )

    except Exception as error:

        print("DOWNLOAD ERROR:", repr(error))

        bot.send_message(
            call.message.chat.id,
            "❌ Зеркашӣ иҷро нашуд.\n\n"
            "Мумкин аст FFmpeg, сайт ё формати файл "
            "дастгирӣ нашавад, ё файл аз 45 MB калон бошад.\n\n"
            "Лутфан баъдтар аз нав кӯшиш кунед."
        )

    finally:

        if job_id:
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

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
