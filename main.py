
import os
import re
import uuid
import shutil
import tempfile
import ipaddress
from urllib.parse import urlparse

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# =========================
# TURBOSAVE SETTINGS
# =========================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not found")

bot = telebot.TeleBot(TOKEN)

MAX_SIZE = 45 * 1024 * 1024

# Temporary download jobs
jobs = {}

# =========================
# URL VALIDATION
# =========================

def valid_url(url):
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        host = parsed.hostname

        if not host or "." not in host:
            return False

        if host.lower() in ("localhost",):
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
    host = urlparse(url).netloc.lower()

    platforms = {
        "instagram.com": "Instagram",
        "youtube.com": "YouTube",
        "youtu.be": "YouTube",
        "tiktok.com": "TikTok",
        "facebook.com": "Facebook",
        "fb.watch": "Facebook",
        "twitter.com": "X",
        "x.com": "X",
        "pinterest.com": "Pinterest"
    }

    for domain, name in platforms.items():
        if host == domain or host.endswith("." + domain):
            return name

    return "Дигар сайтҳо"


# =========================
# START COMMAND
# =========================

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
        "📸 Видео ва аксҳоро аз манбаъҳои "
        "дастгиришаванда қабул мекунем.\n\n"
        "🔗 Ссылкаи маводи иҷозатдодашударо фиристед.",
        reply_markup=keyboard
    )


# =========================
# HELP COMMAND
# =========================

@bot.message_handler(commands=["help"])
def help_command(message):

    bot.reply_to(
        message,
        "📌 Тарзи истифода:\n\n"
        "1. Ссылкаро фиристед.\n"
        "2. Сифатро интихоб кунед.\n"
        "3. Бот маводи дастрасро месанҷад.\n"
        "4. Агар дастгирӣ шавад, файлро мегиред.\n\n"
        "⚠️ Танҳо маводи иҷозатдодашударо истифода баред."
    )


# =========================
# RECEIVE LINK
# =========================

@bot.message_handler(
    content_types=["text"],
    func=lambda m: not m.text.startswith("/")
)
def receive_link(message):

    url = message.text.strip()

    if not valid_url(url):
        bot.reply_to(
            message,
            "❌ Ссылка дуруст нест.\n"
            "Лутфан пайванди HTTP ё HTTPS фиристед."
        )
        return

    platform = get_platform(url)

    job_id = uuid.uuid4().hex[:12]

    jobs[job_id] = {
        "url": url,
        "user": message.from_user.id
    }

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

    bot.reply_to(
        message,
        f"✅ Ссылка қабул шуд!\n\n"
        f"🌐 Платформа: {platform}\n"
        f"📥 Сифати дилхоҳро интихоб кунед:",
        reply_markup=keyboard
    )


# =========================
# DOWNLOAD MEDIA
# =========================

def download_media(url, quality):

    if quality == "best":
        fmt = "best[filesize<45M]/best"
    else:
        fmt = (
            f"best[height<={quality}]"
            f"[filesize<45M]/"
            f"best[height<={quality}]/best"
        )

    with tempfile.TemporaryDirectory() as folder:

        options = {
            "format": fmt,
            "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
            "noplaylist": True,
            "max_filesize": MAX_SIZE,
            "socket_timeout": 20,
            "retries": 2,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
        }

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(url, download=True)

            if not info:
                raise ValueError("Мавод ёфт нашуд")

            path = ydl.prepare_filename(info)

            if not os.path.isfile(path):
                candidates = [
                    os.path.join(folder, name)
                    for name in os.listdir(folder)
                    if os.path.isfile(os.path.join(folder, name))
                ]

                if not candidates:
                    raise ValueError("Файл сохта нашуд")

                path = candidates[0]

            size = os.path.getsize(path)

            if size > MAX_SIZE:
                raise ValueError("Файл аз ҳад калон аст")

            # Keep temporary directory alive while sending
            yield path


# =========================
# QUALITY BUTTONS
# =========================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("q|")
)
def quality_callback(call):

    try:
        _, quality, job_id = call.data.split("|")

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

        bot.answer_callback_query(
            call.id,
            "Зеркашӣ оғоз шуд..."
        )

        status = bot.send_message(
            call.message.chat.id,
            "⏳ Лутфан интизор шавед..."
        )

        try:
            with tempfile.TemporaryDirectory() as folder:

                options = {
                    "format": (
                        "best[filesize<45M]/best"
                        if quality == "best"
                        else
                        f"best[height<={quality}]"
                        f"[filesize<45M]/"
                        f"best[height<={quality}]/best"
                    ),
                    "outtmpl": os.path.join(
                        folder, "%(id)s.%(ext)s"
                    ),
                    "noplaylist": True,
                    "max_filesize": MAX_SIZE,
                    "socket_timeout": 20,
                    "retries": 2,
                    "quiet": True,
                    "no_warnings": True,
                }

                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(
                        job["url"],
                        download=True
                    )

                    if not info:
                        raise ValueError("Мавод дастрас нест")

                    path = ydl.prepare_filename(info)

                    if not os.path.isfile(path):
                        files = os.listdir(folder)

                        if not files:
                            raise ValueError("Файл ёфт нашуд")

                        path = os.path.join(folder, files[0])

                    if os.path.getsize(path) > MAX_SIZE:
                        raise ValueError(
                            "Файл аз 45 MB калон аст"
                        )

                    ext = os.path.splitext(path)[1].lower()

                    with open(path, "rb") as media:

                        if ext in (
                            ".jpg", ".jpeg", ".png", ".webp"
                        ):
                            bot.send_photo(
                                call.message.chat.id,
                                media
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

        finally:
            jobs.pop(job_id, None)

    except Exception as error:

        print("DOWNLOAD ERROR:", str(error))

        bot.send_message(
            call.message.chat.id,
            "❌ Зеркашӣ иҷро нашуд.\n\n"
            "Сабаб метавонад дастгирӣ нашудани сайт, "
            "маҳдудияти дастрасӣ ё андозаи файл бошад."
        )


# =========================
# START BOT
# =========================

print("TurboSave is running...")

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
