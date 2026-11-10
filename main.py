
import os
import re
import html
import shutil
import tempfile
import subprocess
import ipaddress
import traceback
import requests
import telebot
import yt_dlp

from urllib.parse import urlparse, quote_plus
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# =====================================
# SETTINGS
# =====================================

TOKEN = os.getenv("BOT_TOKEN")
AUDD_TOKEN = os.getenv("AUDD_API_TOKEN")
JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN дар GitHub Secrets нест.")

bot = telebot.TeleBot(TOKEN)

# Telegram sending limit: use a conservative limit
MAX_SIZE = 205 * 1024 * 1024

# Telegram cloud Bot API download limit for received files
MAX_INPUT_SIZE = 100 * 1024 * 1024

AUDD_MAX_SIZE = 100 * 1024 * 1024

ALLOWED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
    "pinterest.com",
    "pin.it",
)

user_modes = {}


# =====================================
# MENUS
# =====================================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)

    markup.add(
        InlineKeyboardButton(
            "📥 Видео зеркашӣ",
            callback_data="video"
        ),
        InlineKeyboardButton(
            "🎵 Мусиқӣ ёфтан",
            callback_data="music"
        )
    )

    markup.add(
        InlineKeyboardButton(
            "ℹ️ Ёрӣ",
            callback_data="help"
        )
    )

    return markup


def quality_menu():
    markup = InlineKeyboardMarkup(row_width=2)

    for quality in ("360", "480", "720", "1080"):
        markup.add(
            InlineKeyboardButton(
                f"{quality}p",
                callback_data=f"q_{quality}"
            )
        )

    markup.add(
        InlineKeyboardButton(
            "🎵 MP3",
            callback_data="q_mp3"
        )
    )

    return markup


# =====================================
# URL VALIDATION
# =====================================

def valid_url(url):
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        host = (parsed.hostname or "").lower()

        if not host:
            return False

        try:
            ip = ipaddress.ip_address(host)

            if not ip.is_global:
                return False

        except ValueError:
            pass

        return any(
            host == domain or host.endswith("." + domain)
            for domain in ALLOWED_DOMAINS
        )

    except Exception:
        return False


# =====================================
# FILE HELPERS
# =====================================

def get_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def remove_file(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def find_file(folder, extension=None):
    if not os.path.isdir(folder):
        return None

    ignored = (
        ".part",
        ".ytdl",
        ".temp",
        ".json",
        ".description",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".vtt",
        ".srt"
    )

    candidates = []

    for name in os.listdir(folder):
        path = os.path.join(folder, name)

        if not os.path.isfile(path):
            continue

        lower_name = name.lower()

        if lower_name.endswith(ignored):
            continue

        if extension:
            if not lower_name.endswith(extension.lower()):
                continue
        else:
            if not lower_name.endswith(
                (".mp4", ".mkv", ".webm", ".mov", ".mp3", ".m4a", ".ogg")
            ):
                continue

        if get_size(path) > 0:
            candidates.append(path)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: get_size(item),
        reverse=True
    )

    return candidates[0]


# =====================================
# FFMPEG
# =====================================

def check_ffmpeg():
    return shutil.which("ffmpeg") is not None


def convert_to_mp3(source, destination, seconds=12):
    if not check_ffmpeg():
        raise RuntimeError("FFmpeg насб нашудааст.")

    command = [
        "ffmpeg",
        "-y",
        "-i", source,
        "-vn",
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        "-t", str(seconds),
        destination
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120
    )

    if result.returncode != 0:
        print("FFmpeg error:", result.stderr.decode(errors="ignore")[-2000:])
        raise RuntimeError("Табдили MP3 иҷро нашуд.")

    if not os.path.isfile(destination):
        raise RuntimeError("Файли MP3 сохта нашуд.")

    return destination


# =====================================
# AUDD RECOGNITION
# =====================================

def recognize_audio_file(path):
    if not AUDD_TOKEN:
        return {
            "error": "AUDD_API_TOKEN дар GitHub Secrets нест."
        }

    if get_size(path) > AUDD_MAX_SIZE:
        return {
            "error": "Файл барои AudD калон аст."
        }

    try:
        with open(path, "rb") as audio:
            response = requests.post(
                "https://api.audd.io/",
                data={
                    "api_token": AUDD_TOKEN,
                    "return": "spotify,apple_music"
                },
                files={
                    "file": audio
                },
                timeout=90
            )

        response.raise_for_status()
        data = response.json()

        if data.get("status") != "success":
            print("AudD response:", data)
            return {
                "error": "AudD сурудро муайян карда натавонист."
            }

        return data.get("result")

    except requests.RequestException as error:
        print("AudD request error:", repr(error))
        return {
            "error": "Ба AudD пайваст нашуд."
        }

    except Exception as error:
        print("AudD error:", repr(error))
        return {
            "error": "Шинохти мусиқӣ иҷро нашуд."
        }


# =====================================
# MUSIC MESSAGE
# =====================================

def music_message(song):
    title = song.get("title") or "Номаълум"
    artist = song.get("artist") or "Номаълум"

    text = (
        "🎵 <b>Суруд ёфт шуд!</b>\n\n"
        f"🎼 Ном: <b>{html.escape(title)}</b>\n"
        f"👤 Иҷрокунанда: <b>{html.escape(artist)}</b>\n"
    )

    spotify = song.get("spotify")
    apple = song.get("apple_music")

    if isinstance(spotify, dict):
        url = spotify.get("external_urls", {}).get("spotify")

        if url:
            text += (
                f'\n🟢 <a href="{html.escape(url, quote=True)}">'
                "Spotify</a>"
            )

    if isinstance(apple, dict):
        url = apple.get("url")

        if url:
            text += (
                f'\n🍎 <a href="{html.escape(url, quote=True)}">'
                "Apple Music</a>"
            )

    query = quote_plus(f"{title} {artist}")

    soundcloud = (
        f"https://soundcloud.com/search/sounds?q={query}"
    )

    bandcamp = (
        f"https://bandcamp.com/search?q={query}"
    )

    text += (
        "\n\n🔎 <b>Ҷустуҷӯи мусиқӣ:</b>"
        f'\n🎧 <a href="{soundcloud}">SoundCloud</a>'
        f'\n🎸 <a href="{bandcamp}">Bandcamp</a>'
    )

    return text


# =====================================
# JAMENDO
# =====================================

def download_jamendo_music(title, artist, folder):
    if not JAMENDO_CLIENT_ID:
        print("JAMENDO_CLIENT_ID missing.")
        return None

    if not title or not artist:
        return None

    try:
        response = requests.get(
            "https://api.jamendo.com/v3.0/tracks/",
            params={
                "client_id": JAMENDO_CLIENT_ID,
                "format": "json",
                "limit": 10,
                "namesearch": f"{title} {artist}",
                "audioformat": "mp32"
            },
            timeout=30
        )

        response.raise_for_status()

        tracks = response.json().get("results", [])

        wanted_title = normalize_text(title)
        wanted_artist = normalize_text(artist)

        for track in tracks:
            if not track.get("audiodownload_allowed"):
                continue

            found_title = normalize_text(track.get("name"))
            found_artist = normalize_text(track.get("artist_name"))

            title_match = (
                wanted_title in found_title
                or found_title in wanted_title
            )

            artist_match = (
                wanted_artist in found_artist
                or found_artist in wanted_artist
            )

            if not title_match or not artist_match:
                continue

            download_url = track.get("audiodownload")

            if not download_url:
                continue

            result = requests.get(
                download_url,
                stream=True,
                timeout=60
            )

            result.raise_for_status()

            output = os.path.join(folder, "jamendo.mp3")
            total = 0

            try:
                with open(output, "wb") as file:
                    for chunk in result.iter_content(65536):
                        if not chunk:
                            continue

                        total += len(chunk)

                        if total > MAX_SIZE:
                            raise RuntimeError(
                                "Jamendo файл аз ҳад калон аст."
                            )

                        file.write(chunk)

            finally:
                result.close()

            if total > 1000:
                return output

            remove_file(output)

    except Exception as error:
        print("Jamendo error:", repr(error))
        traceback.print_exc()

    return None


# =====================================
# RECOGNIZE AND SEND MUSIC
# =====================================

def recognize_and_send_music(chat_id, source_path):
    folder = tempfile.mkdtemp(prefix="music_")

    try:
        mp3_path = os.path.join(folder, "recognize.mp3")

        convert_to_mp3(
            source_path,
            mp3_path,
            seconds=12
        )

        song = recognize_audio_file(mp3_path)

        if not song:
            bot.send_message(
                chat_id,
                "❌ Суруд муайян карда нашуд."
            )
            return

        if song.get("error"):
            bot.send_message(
                chat_id,
                "⚠️ " + song["error"]
            )
            return

        bot.send_message(
            chat_id,
            music_message(song),
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        title = song.get("title") or ""
        artist = song.get("artist") or ""

        found = download_jamendo_music(
            title,
            artist,
            folder
        )

        if found:
            if get_size(found) > MAX_SIZE:
                bot.send_message(
                    chat_id,
                    "⚠️ Файли мусиқӣ хеле калон аст."
                )
                return

            with open(found, "rb") as audio:
                bot.send_audio(
                    chat_id,
                    audio,
                    title=title[:64],
                    performer=artist[:64],
                    caption="🎵 Версияи иҷозатдодашуда аз Jamendo"
                )

        else:
            bot.send_message(
                chat_id,
                "ℹ️ Дар Jamendo нусхаи иҷозатдодашуда ёфт нашуд.\n\n"
                "Метавонӣ аз пайвандҳои SoundCloud ё Bandcamp "
                "сурудро ҷустуҷӯ кунӣ."
            )

    except Exception as error:
        print("Recognition error:", repr(error))
        traceback.print_exc()

        bot.send_message(
            chat_id,
            "❌ Ҳангоми шинохти мусиқӣ хато рух дод."
        )

    finally:
        shutil.rmtree(folder, ignore_errors=True)


# =====================================
# VIDEO DOWNLOAD
# =====================================

def download_video(url, quality, folder):
    if not check_ffmpeg():
        raise RuntimeError("FFmpeg насб нашудааст.")

    output = os.path.join(
        folder,
        "%(title).80s.%(ext)s"
    )

    formats = {
        "360": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
        "480": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "720": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    }

    options = {
        "outtmpl": output,
        "format": formats.get(quality, formats["720"]),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "max_filesize": MAX_SIZE,
        "socket_timeout": 40,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 2,
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4"
            }
        ]
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    path = find_file(folder, ".mp4")

    if not path:
        path = find_file(folder)

    if not path:
        raise RuntimeError("Файли видео сохта нашуд.")

    if get_size(path) > MAX_SIZE:
        raise RuntimeError("Ҳаҷми видео аз ҳадди иҷозатшуда зиёд аст.")

    return path


# =====================================
# AUDIO DOWNLOAD
# =====================================

def download_audio(url, folder):
    output = os.path.join(
        folder,
        "%(title).80s.%(ext)s"
    )

    options = {
        "outtmpl": output,
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "max_filesize": MAX_SIZE,
        "socket_timeout": 40,
        "retries": 3,
        "fragment_retries": 3,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }
        ]
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    path = find_file(folder, ".mp3")

    if not path:
        raise RuntimeError("Файли MP3 сохта нашуд.")

    if get_size(path) > MAX_SIZE:
        raise RuntimeError("Ҳаҷми MP3 аз ҳадди иҷозатшуда зиёд аст.")

    return path


# =====================================
# START
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    user_modes.pop(message.chat.id, None)

    bot.send_message(
        message.chat.id,
        "👋 Хуш омадед ба <b>TurboSave</b>!\n\n"
        "📥 Видео зеркашӣ кун.\n"
        "🎵 Мусиқии дохили видеоро ёб.",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


# =====================================
# HELP
# =====================================

@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "📌 <b>Тарзи истифода:</b>\n\n"
        "1. Видео зеркашӣ — пайвандро фирист.\n"
        "2. Сифатро интихоб кун.\n"
        "3. Барои мусиқӣ тугмаи «Мусиқӣ ёфтан»-ро пахш кун.\n"
        "4. Видео ё аудиоро низ метавонӣ ба бот фиристӣ.\n\n"
        "Дастгирӣ: YouTube, Instagram, TikTok, Facebook, "
        "X ва Pinterest.\n\n"
        "⚠️ Маводи хусусӣ ё маҳдудро бот кушода наметавонад.",
        parse_mode="HTML"
    )


# =====================================
# CALLBACKS
# =====================================

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id

    if call.data == "video":
        bot.answer_callback_query(call.id)

        bot.send_message(
            chat_id,
            "📥 Аввал сифати видеоро интихоб кун:",
            reply_markup=quality_menu()
        )

    elif call.data == "music":
        bot.answer_callback_query(call.id)

        user_modes[chat_id] = "music"

        bot.send_message(
            chat_id,
            "🎵 Пайванди видео ё худи файлро фирист."
        )

    elif call.data == "help":
        bot.answer_callback_query(call.id)
        help_command(call.message)

    elif call.data.startswith("q_"):
        quality = call.data.replace("q_", "")

        bot.answer_callback_query(call.id)

        if quality == "mp3":
            user_modes[chat_id] = "music"

            bot.send_message(
                chat_id,
                "🎵 Пайванди видеоро фирист."
            )

        elif quality in ("360", "480", "720", "1080"):
            user_modes[chat_id] = "video_" + quality

            bot.send_message(
                chat_id,
                f"✅ Сифати {quality}p интихоб шуд.\n\n"
                "Акнун пайванди видеоро фирист."
            )

        else:
            bot.send_message(
                chat_id,
                "❌ Ин интихоб дастгирӣ намешавад."
            )

    else:
        bot.answer_callback_query(
            call.id,
            "Ин тугма дигар фаъол нест."
        )


# =====================================
# RECEIVE LINKS
# =====================================

@bot.message_handler(
    content_types=["text"],
    func=lambda message: bool(message.text)
    and not message.text.startswith("/")
)
def receive_link(message):
    chat_id = message.chat.id
    url = message.text.strip()

    if not valid_url(url):
        bot.send_message(
            chat_id,
            "❌ Пайванди дурусти сайтро фирист."
        )
        return

    mode = user_modes.get(chat_id, "video_720")

    folder = tempfile.mkdtemp(prefix="download_")

    try:
        bot.send_message(
            chat_id,
            "⏳ Кор оғоз шуд. Каме интизор шав..."
        )

        if mode == "music":
            path = download_audio(
                url,
                folder
            )

            if not path:
                raise RuntimeError("Мусиқӣ гирифта нашуд.")

            if get_size(path) > MAX_SIZE:
                raise RuntimeError("Файли мусиқӣ хеле калон аст.")

            with open(path, "rb") as audio:
                bot.send_audio(
                    chat_id,
                    audio,
                    caption="🎵 TurboSave MP3"
                )

            recognize_and_send_music(
                chat_id,
                path
            )

        else:
            quality = mode.replace("video_", "")

            path = download_video(
                url,
                quality,
                folder
            )

            if not path:
                raise RuntimeError("Видео ёфт нашуд.")

            size = get_size(path)

            if size > MAX_SIZE:
                raise RuntimeError(
                    "Ҳаҷми видео аз ҳадди иҷозатшуда зиёд аст."
                )

            with open(path, "rb") as video:
                bot.send_video(
                    chat_id,
                    video,
                    caption=f"📥 TurboSave | {quality}p",
                    supports_streaming=True
                )

    except Exception as error:
        print("DOWNLOAD ERROR:", repr(error))
        traceback.print_exc()

        bot.send_message(
            chat_id,
            "❌ Зеркашӣ иҷро нашуд.\n\n"
            f"Сабаб: {str(error)[:600]}"
        )

    finally:
        shutil.rmtree(folder, ignore_errors=True)
        user_modes.pop(chat_id, None)


# =====================================
# RECEIVE TELEGRAM MEDIA
# =====================================

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

    if media.file_size and media.file_size > MAX_INPUT_SIZE:
        bot.send_message(
            chat_id,
            "⚠️ Файл аз 20 MB калон аст."
        )
        return

    folder = tempfile.mkdtemp(prefix="telegram_media_")

    try:
        file_info = bot.get_file(media.file_id)

        extension = os.path.splitext(
            file_info.file_path
        )[1].lower()

        allowed_extensions = (
            ".mp3",
            ".m4a",
            ".aac",
            ".ogg",
            ".oga",
            ".wav",
            ".flac",
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".3gp"
        )

        if extension not in allowed_extensions:
            bot.send_message(
                chat_id,
                "❌ Ин навъи файл дастгирӣ намешавад."
            )
            return

        bot.send_message(
            chat_id,
            "🔎 Файл қабул шуд. Мусиқиро меҷӯям..."
        )

        downloaded = bot.download_file(
            file_info.file_path
        )

        source = os.path.join(
            folder,
            "input" + extension
        )

        with open(source, "wb") as file:
            file.write(downloaded)

        if get_size(source) > MAX_INPUT_SIZE:
            bot.send_message(
                chat_id,
                "⚠️ Файл аз ҳадди иҷозатшуда калон аст."
            )
            return

        recognize_and_send_music(
            chat_id,
            source
        )

    except Exception as error:
        print("MEDIA ERROR:", repr(error))
        traceback.print_exc()

        bot.send_message(
            chat_id,
            "❌ Файл коркард нашуд."
        )

    finally:
        shutil.rmtree(folder, ignore_errors=True)


# =====================================
# RUN BOT
# =====================================

print("TurboSave is running...")

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
