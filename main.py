
import os
import re
import uuid
import shutil
import tempfile
import subprocess
import ipaddress
import socket
from urllib.parse import urlparse

import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp


# =========================================
# TURBOSAVE SETTINGS
# =========================================

TOKEN = os.getenv("BOT_TOKEN")
AUDD_TOKEN = os.getenv("AUDD_API_TOKEN")
JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN дар GitHub Secrets гузошта нашудааст.")

bot = telebot.TeleBot(TOKEN)

MAX_SIZE = 45 * 1024 * 1024
AUDD_MAX_SIZE = 10 * 1024 * 1024
MAX_MUSIC_INPUT = 20 * 1024 * 1024

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Барои ҳар корбар пайванди охиринаш нигоҳ дошта мешавад.
user_jobs = {}

ALLOWED_DOMAINS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "fb.watch",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "pinterest.com",
    "www.pinterest.com",
    "pin.it",
}


# =========================================
# URL VALIDATION
# =========================================

def valid_url(url):
    try:
        parsed = urlparse(url.strip())

        if parsed.scheme not in ("http", "https"):
            return False

        if not parsed.hostname:
            return False

        if parsed.username or parsed.password:
            return False

        host = parsed.hostname.lower()

        if host not in ALLOWED_DOMAINS:
            return False

        # Пешгирӣ аз URL-ҳои маҳаллӣ ва IP-ҳои хусусӣ.
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                return False
        except ValueError:
            pass

        return True

    except Exception:
        return False


def detect_platform(url):
    host = urlparse(url).hostname or ""
    host = host.lower()

    if "instagram.com" in host:
        return "Instagram"
    if "youtube.com" in host or "youtu.be" in host:
        return "YouTube"
    if "tiktok.com" in host:
        return "TikTok"
    if "facebook.com" in host or "fb.watch" in host:
        return "Facebook"
    if "twitter.com" in host or "x.com" in host:
        return "X"
    if "pinterest.com" in host or "pin.it" in host:
        return "Pinterest"

    return "Сомона"


# =========================================
# KEYBOARDS
# =========================================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "📥 Оғози зеркашӣ",
            callback_data="start_download"
        ),
        InlineKeyboardButton(
            "🎧 Шинохтани мусиқӣ",
            callback_data="recognize"
        ),
        InlineKeyboardButton(
            "ℹ️ Дастур",
            callback_data="help"
        )
    )
    return markup


def download_menu():
    markup = InlineKeyboardMarkup(row_width=2)

    markup.add(
        InlineKeyboardButton(
            "🎬 Видео",
            callback_data="download_video"
        ),
        InlineKeyboardButton(
            "🎵 Мусиқӣ MP3",
            callback_data="download_music"
        )
    )
    return markup


def quality_menu():
    markup = InlineKeyboardMarkup(row_width=2)

    markup.add(
        InlineKeyboardButton(
            "360p",
            callback_data="quality_360"
        ),
        InlineKeyboardButton(
            "720p",
            callback_data="quality_720"
        ),
        InlineKeyboardButton(
            "1080p",
            callback_data="quality_1080"
        ),
        InlineKeyboardButton(
            "Беҳтарин сифат",
            callback_data="quality_best"
        )
    )
    return markup


# =========================================
# START / HELP
# =========================================

@bot.message_handler(commands=["start"])
def start(message):
    text = (
        "👋 Хуш омадед ба TurboSave!\n\n"
        "📥 Видео ва мусиқиро аз сомонаҳои дастгиришаванда "
        "зеркашӣ кунед.\n\n"
        "🎧 Метавонед мусиқиро низ шинохта гиред.\n\n"
        "Барои оғоз тугмаро зер кунед."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=main_menu()
    )


@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "📌 Дастури TurboSave\n\n"
        "1. Тугмаи «Оғози зеркашӣ»-ро пахш кунед.\n"
        "2. Пайванди видео ё постро фиристед.\n"
        "3. Видео ё мусиқиро интихоб кунед.\n\n"
        "Барои шинохтани мусиқӣ тугмаи "
        "«Шинохтани мусиқӣ»-ро истифода баред."
    )


# =========================================
# CALLBACKS
# =========================================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data

    bot.answer_callback_query(call.id)

    if data == "start_download":
        bot.send_message(
            chat_id,
            "🔗 Пайванди видео ё постро фиристед."
        )
        return

    if data == "recognize":
        bot.send_message(
            chat_id,
            "🎧 Видео, аудио ё файли мусиқиро фиристед.\n\n"
            "Ман кӯшиш мекунам номи суруд ва иҷрогарро муайян кунам."
        )
        return

    if data == "help":
        bot.send_message(
            chat_id,
            "📌 Пайванди видео ё постро фиристед.\n"
            "Баъд намуди файлро интихоб кунед."
        )
        return

    if data in ("download_video", "download_music"):
        if user_id not in user_jobs:
            bot.send_message(
                chat_id,
                "⚠️ Аввал пайванди видео ё постро фиристед."
            )
            return

        if data == "download_video":
            bot.send_message(
                chat_id,
                "🎬 Сифати видеоро интихоб кунед:",
                reply_markup=quality_menu()
            )
        else:
            bot.send_message(
                chat_id,
                "🎵 Ҳоло видео гирифта мешавад, мусиқӣ шинохта "
                "мешавад ва агар суруд дар каталоги иҷозатдодаи "
                "Jamendo бошад, MP3-и пурра фиристода мешавад."
            )
            download_callback(
                chat_id,
                user_id,
                "music",
                "best"
            )
        return

    if data.startswith("quality_"):
        quality = data.replace("quality_", "")

        if user_id not in user_jobs:
            bot.send_message(
                chat_id,
                "⚠️ Пайвандро аз нав фиристед."
            )
            return

        download_callback(
            chat_id,
            user_id,
            "video",
            quality
        )
        return


# =========================================
# DOWNLOAD SETTINGS
# =========================================

def ydl_options(folder, mode="video", quality="best"):
    output = os.path.join(folder, "%(title).80s_%(id)s.%(ext)s")

    options = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 25,
        "max_filesize": MAX_SIZE,
        "overwrites": True,
    }

    if mode == "music":
        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })

    else:
        if quality == "360":
            fmt = "best[height<=360]/best"
        elif quality == "720":
            fmt = "best[height<=720]/best"
        elif quality == "1080":
            fmt = "best[height<=1080]/best"
        else:
            fmt = "best"

        options.update({
            "format": fmt,
            "merge_output_format": "mp4",
        })

    return options


# =========================================
# FILE HELPERS
# =========================================

def find_file(folder, mode):
    if not os.path.isdir(folder):
        return None

    files = []

    for name in os.listdir(folder):
        path = os.path.join(folder, name)

        if not os.path.isfile(path):
            continue

        if name.endswith((".part", ".ytdl", ".tmp")):
            continue

        size = os.path.getsize(path)

        if size <= 0 or size > MAX_SIZE:
            continue

        if mode == "music":
            if name.lower().endswith(".mp3"):
                files.append(path)
        else:
            if name.lower().endswith(
                (".mp4", ".mkv", ".webm", ".mov", ".m4v")
            ):
                files.append(path)

    if not files:
        return None

    return max(files, key=os.path.getsize)


def safe_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name[:80] or "TurboSave"


# =========================================
# AUDD MUSIC RECOGNITION
# =========================================

def recognize_audio_file(file_path, folder):
    if not AUDD_TOKEN:
        return None

    if not shutil.which("ffmpeg"):
        return None

    converted = os.path.join(folder, "audd_sample.mp3")

    try:
        command = [
            "ffmpeg",
            "-y",
            "-i", file_path,
            "-t", "12",
            "-vn",
            "-ac", "1",
            "-ar", "44100",
            "-b:a", "96k",
            converted
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45
        )

        if result.returncode != 0:
            return None

        if not os.path.exists(converted):
            return None

        if os.path.getsize(converted) > AUDD_MAX_SIZE:
            return None

        with open(converted, "rb") as audio:
            response = requests.post(
                "https://api.audd.io/",
                data={
                    "api_token": AUDD_TOKEN,
                    "return": "spotify,apple_music",
                },
                files={
                    "file": audio
                },
                timeout=60
            )

        response.raise_for_status()
        data = response.json()

        if data.get("status") != "success":
            return None

        song = data.get("result")

        if not song:
            return None

        return song

    except Exception as error:
        print("AudD error:", error)
        return None


def music_message(song):
    title = song.get("title") or "Номаълум"
    artist = song.get("artist") or "Номаълум"

    text = (
        "🎧 **Мусиқӣ ёфт шуд!**\n\n"
        f"🎵 Ном: {title}\n"
        f"👤 Иҷрокунанда: {artist}\n"
    )

    spotify = song.get("spotify")
    apple = song.get("apple_music")

    if isinstance(spotify, dict) and spotify.get("external_urls"):
        link = spotify["external_urls"].get("spotify")
        if link:
            text += f"\n🟢 Spotify: {link}"

    if isinstance(apple, dict) and apple.get("url"):
        text += f"\n🍎 Apple Music: {apple['url']}"

    return text


# =========================================
# JAMENDO LICENSED MP3 SEARCH
# =========================================

def download_jamendo_music(song, folder):
    if not JAMENDO_CLIENT_ID:
        print("JAMENDO_CLIENT_ID missing")
        return None

    title = song.get("title", "").strip()
    artist = song.get("artist", "").strip()

    if not title:
        return None

    search_text = f"{title} {artist}".strip()

    try:
        response = requests.get(
            "https://api.jamendo.com/v3.0/tracks/",
            params={
                "client_id": JAMENDO_CLIENT_ID,
                "format": "json",
                "search": search_text,
                "limit": 10,
                "order": "relevance",
                "audioformat": "mp32",
                "audiodlformat": "mp32",
            },
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])

        if not results:
            return None

        # Аввал сурудеро интихоб мекунем, ки Jamendo иҷозати
        # зеркашии аудиоро барои он нишон додааст.
        for track in results:
            if not track.get("audiodownload_allowed"):
                continue

            download_url = track.get("audiodownload")

            if not download_url:
                continue

            track_title = track.get("name", "Unknown")
            track_artist = track.get("artist_name", "Unknown")

            # Барои кам кардани хатои мувофиқат,
            # ном ё иҷрогари натиҷа бояд бо AudD монанд бошад.
            wanted_title = re.sub(
                r"[^a-z0-9]",
                "",
                title.lower()
            )
            found_title = re.sub(
                r"[^a-z0-9]",
                "",
                track_title.lower()
            )

            wanted_artist = re.sub(
                r"[^a-z0-9]",
                "",
                artist.lower()
            )
            found_artist = re.sub(
                r"[^a-z0-9]",
                "",
                track_artist.lower()
            )

            title_match = (
                wanted_title in found_title
                or found_title in wanted_title
            ) if wanted_title and found_title else False

            artist_match = (
                wanted_artist in found_artist
                or found_artist in wanted_artist
            ) if wanted_artist and found_artist else False

            if not title_match and not artist_match:
                continue

            file_path = os.path.join(
                folder,
                "jamendo_music.mp3"
            )

            with requests.get(
                download_url,
                stream=True,
                timeout=60
            ) as download_response:

                download_response.raise_for_status()

                total = 0

                with open(file_path, "wb") as output:
                    for chunk in download_response.iter_content(
                        chunk_size=64 * 1024
                    ):
                        if not chunk:
                            continue

                        total += len(chunk)

                        if total > MAX_SIZE:
                            output.close()
                            os.remove(file_path)
                            return None

                        output.write(chunk)

            if not os.path.exists(file_path):
                continue

            if os.path.getsize(file_path) <= 0:
                continue

            return {
                "path": file_path,
                "title": track_title,
                "artist": track_artist,
            }

        return None

    except Exception as error:
        print("Jamendo error:", error)
        return None


# =========================================
# RECOGNIZE AND SEND FULL MUSIC
# =========================================

def recognize_and_send_music(chat_id, file_path, folder):
    if not AUDD_TOKEN:
        bot.send_message(
            chat_id,
            "⚠️ AUDD_API_TOKEN дар GitHub Secrets гузошта нашудааст."
        )
        return

    bot.send_message(
        chat_id,
        "🔎 Мусиқӣ шинохта шуда истодааст..."
    )

    song = recognize_audio_file(file_path, folder)

    if not song:
        bot.send_message(
            chat_id,
            "❌ Мусиқиро муайян карда натавонистам.\n\n"
            "Кӯшиш кунед файли равшантар ё порчаи дигари мусиқиро фиристед."
        )
        return

    bot.send_message(
        chat_id,
        music_message(song),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

    bot.send_message(
        chat_id,
        "🎵 Ҳоло суруди пурра дар каталоги иҷозатдодаи Jamendo ҷустуҷӯ мешавад..."
    )

    found = download_jamendo_music(song, folder)

    if not found:
        bot.send_message(
            chat_id,
            "ℹ️ Ин суруд дар каталоги зеркашии иҷозатдодаи Jamendo "
            "ёфт нашуд.\n\n"
            "Ман наметавонам MP3-и пурраи онро аз манбаи "
            "бе иҷозат фиристам. Агар пайванди Spotify ё Apple Music "
            "дар боло бошад, метавонед аз он ҷо гӯш кунед."
        )
        return

    with open(found["path"], "rb") as audio:
        bot.send_audio(
            chat_id,
            audio,
            title=found["title"],
            performer=found["artist"],
            caption=(
                "🎵 Суруди пурра аз каталоги Jamendo\n"
                "✅ Зеркашӣ барои ин трек иҷозат дода шудааст."
            )
        )


# =========================================
# DOWNLOAD VIDEO / MUSIC FROM LINK
# =========================================

def download_callback(chat_id, user_id, mode, quality):
    url = user_jobs.get(user_id)

    if not url:
        bot.send_message(
            chat_id,
            "⚠️ Пайванд ёфт нашуд. Лутфан аз нав фиристед."
        )
        return

    platform = detect_platform(url)

    status = bot.send_message(
        chat_id,
        f"⏳ Аз {platform} зеркашӣ оғоз шуд..."
    )

    try:
        with tempfile.TemporaryDirectory() as folder:
            options = ydl_options(
                folder,
                mode=mode,
                quality=quality
            )

            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])

            file_path = find_file(folder, mode)

            if not file_path:
                bot.edit_message_text(
                    "❌ Файл гирифта нашуд ё аз лимити 45 MB калон аст.\n\n"
                    "Барои YouTube баъзан худи сомона зеркаширо маҳдуд мекунад.",
                    chat_id,
                    status.message_id
                )
                return

            if mode == "music":
                bot.edit_message_text(
                    "🎧 Мусиқии видео гирифта шуд. Ҳоло сурудро мешиносам...",
                    chat_id,
                    status.message_id
                )

                recognize_and_send_music(
                    chat_id,
                    file_path,
                    folder
                )
                return

            bot.edit_message_text(
                "📤 Файл омода шуд. Ба Telegram фиристода мешавад...",
                chat_id,
                status.message_id
            )

            with open(file_path, "rb") as media:
                bot.send_video(
                    chat_id,
                    media,
                    supports_streaming=True,
                    caption=f"✅ Боргирӣ аз {platform}\n🤖 TurboSave"
                )

    except Exception as error:
        print("Download error:", error)

        bot.send_message(
            chat_id,
            "❌ Зеркашӣ иҷро нашуд.\n\n"
            "Сабаб метавонад маҳдудияти худи сомона, "
            "формати дастгиринашаванда ё калон будани файл бошад.\n\n"
            "Баъдтар аз нав санҷед."
        )

    finally:
        user_jobs.pop(user_id, None)


# =========================================
# RECEIVE LINKS
# =========================================

@bot.message_handler(
    func=lambda message: bool(message.text)
    and not message.text.startswith("/")
)
def receive_link(message):
    url = message.text.strip()
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not valid_url(url):
        bot.send_message(
            chat_id,
            "⚠️ Пайванди дурустро фиристед.\n\n"
            "TurboSave Instagram, YouTube, TikTok, Facebook, "
            "X ва Pinterest-ро дастгирӣ мекунад."
        )
        return

    user_jobs[user_id] = url

    platform = detect_platform(url)

    bot.send_message(
        chat_id,
        f"✅ Пайванд қабул шуд: {platform}\n\n"
        "Чиро мехоҳед?",
        reply_markup=download_menu()
    )


# =========================================
# RECEIVE AUDIO / VIDEO / DOCUMENT
# =========================================

@bot.message_handler(
    content_types=[
        "audio",
        "voice",
        "video",
        "video_note",
        "document"
    ]
)
def receive_media(message):
    chat_id = message.chat.id

    media = (
        message.audio
        or message.voice
        or message.video
        or message.video_note
        or message.document
    )

    if not media:
        return

    file_size = getattr(media, "file_size", 0) or 0

    if file_size > MAX_MUSIC_INPUT:
        bot.send_message(
            chat_id,
            "⚠️ Барои шинохтани мусиқӣ файл бояд аз 20 MB зиёд набошад."
        )
        return

    if not AUDD_TOKEN:
        bot.send_message(
            chat_id,
            "⚠️ AUDD_API_TOKEN дар GitHub Secrets гузошта нашудааст."
        )
        return

    status = bot.send_message(
        chat_id,
        "⏳ Файл қабул шуд. Мусиқӣ шинохта мешавад..."
    )

    try:
        with tempfile.TemporaryDirectory() as folder:
            file_info = bot.get_file(media.file_id)

            downloaded = bot.download_file(
                file_info.file_path
            )

            extension = os.path.splitext(
                file_info.file_path
            )[1]

            if not extension:
                extension = ".bin"

            input_path = os.path.join(
                folder,
                "input" + extension
            )

            with open(input_path, "wb") as output:
                output.write(downloaded)

            if os.path.getsize(input_path) > MAX_MUSIC_INPUT:
                bot.send_message(
                    chat_id,
                    "⚠️ Файл аз лимити 20 MB калон аст."
                )
                return

            bot.edit_message_text(
                "🔎 Мусиқӣ шинохта мешавад...",
                chat_id,
                status.message_id
            )

            recognize_and_send_music(
                chat_id,
                input_path,
                folder
            )

    except Exception as error:
        print("Receive media error:", error)

        bot.send_message(
            chat_id,
            "❌ Файлро коркард карда натавонистам. "
            "Лутфан бори дигар санҷед."
        )


# =========================================
# START BOT
# =========================================

print("TurboSave is running...")

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
