
import os
import re
import glob
import asyncio
import logging
import tempfile
import shutil
import requests
import yt_dlp
import instaloader

from html.parser import HTMLParser
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =====================================
# SETTINGS
# =====================================

TOKEN = os.getenv("BOT_TOKEN")

MAX_SIZE = 49 * 1024 * 1024

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN дар GitHub Secrets ёфт нашуд."
    )


# =====================================
# DOWNLOAD FILE
# =====================================

def download_file(url, filename):

    response = requests.get(
        url,
        stream=True,
        timeout=90,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    with open(filename, "wb") as file:

        for chunk in response.iter_content(
            1024 * 1024
        ):

            if chunk:
                file.write(chunk)

    if (
        not os.path.exists(filename)
        or os.path.getsize(filename) == 0
    ):
        raise ValueError(
            "Файл холӣ ё зеркашинашуда аст."
        )


# =====================================
# FIND DOWNLOADED FILE
# =====================================

def find_downloaded_file(folder, prefix):

    files = glob.glob(
        os.path.join(folder, prefix + "*")
    )

    files = [
        f for f in files
        if os.path.isfile(f)
        and not f.endswith(
            (".part", ".ytdl", ".json")
        )
    ]

    if not files:
        raise ValueError(
            "Файли зеркашидашуда ёфт нашуд."
        )

    return max(
        files,
        key=os.path.getsize
    )


# =====================================
# YT-DLP DOWNLOADER
# =====================================

def download_with_ytdlp(url, folder, prefix):

    os.makedirs(
        folder,
        exist_ok=True
    )

    output = os.path.join(
        folder,
        prefix + "_%(id)s.%(ext)s"
    )

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:

        ydl.extract_info(
            url,
            download=True
        )

    filename = find_downloaded_file(
        folder,
        prefix
    )

    return [
        (filename, "video")
    ]


# =====================================
# INSTAGRAM DOWNLOADER
# =====================================

def download_instagram(url, folder):

    os.makedirs(
        folder,
        exist_ok=True
    )

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            "Пайванди Instagram нодуруст аст."
        )

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

    # CAROUSEL

    if post.typename == "GraphSidecar":

        for index, node in enumerate(
            post.get_sidecar_nodes(),
            start=1
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

            download_file(
                media_url,
                filename
            )

            results.append(
                (filename, media_type)
            )

        return results

    # PHOTO

    if not post.is_video:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg"
        )

        download_file(
            post.url,
            filename
        )

        return [
            (filename, "photo")
        ]

    # VIDEO

    filename = os.path.join(
        folder,
        "instagram_video.mp4"
    )

    download_file(
        post.video_url,
        filename
    )

    return [
        (filename, "video")
    ]


# =====================================
# YOUTUBE DOWNLOADER
# =====================================

def download_youtube(url, folder):

    if not re.search(
        r"(youtube\.com|youtu\.be)",
        url,
        re.IGNORECASE
    ):
        raise ValueError(
            "Пайванди YouTube нодуруст аст."
        )

    return download_with_ytdlp(
        url,
        folder,
        "youtube"
    )


# =====================================
# TIKTOK DOWNLOADER
# =====================================

def download_tiktok(url, folder):

    if not re.search(
        r"(tiktok\.com|vm\.tiktok\.com)",
        url,
        re.IGNORECASE
    ):
        raise ValueError(
            "Пайванди TikTok нодуруст аст."
        )

    return download_with_ytdlp(
        url,
        folder,
        "tiktok"
    )


# =====================================
# FACEBOOK PHOTO PARSER
# =====================================

class FacebookMetaParser(HTMLParser):

    def __init__(self):

        super().__init__()

        self.meta = {}

    def handle_starttag(self, tag, attrs):

        if tag.lower() != "meta":
            return

        data = dict(attrs)

        key = (
            data.get("property")
            or data.get("name")
        )

        value = data.get("content")

        if key and value:

            self.meta[key.lower()] = value


# =====================================
# FACEBOOK PHOTO DOWNLOADER
# =====================================

def download_facebook_photo(url, folder):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=60,
        allow_redirects=True
    )

    response.raise_for_status()

    parser = FacebookMetaParser()

    parser.feed(
        response.text
    )

    image_url = (
        parser.meta.get("og:image")
        or parser.meta.get("og:image:secure_url")
        or parser.meta.get("twitter:image")
    )

    if not image_url:

        raise ValueError(
            "Facebook акси дастрасро пешниҳод накард. "
            "Шояд пост хусусӣ бошад."
        )

    if parser.meta.get(
        "og:type",
        ""
    ).startswith("video"):

        raise ValueError(
            "Ин пайванд видео аст, на акси Facebook."
        )

    image_response = requests.get(
        image_url,
        headers={
            "User-Agent": headers["User-Agent"],
            "Referer": "https://www.facebook.com/"
        },
        stream=True,
        timeout=90
    )

    image_response.raise_for_status()

    content_type = image_response.headers.get(
        "Content-Type",
        ""
    ).lower()

    if not content_type.startswith("image/"):

        raise ValueError(
            "Facebook файли аксро барнагардонд."
        )

    filename = os.path.join(
        folder,
        "facebook_photo.jpg"
    )

    with open(filename, "wb") as file:

        for chunk in image_response.iter_content(
            1024 * 1024
        ):

            if chunk:
                file.write(chunk)

    with open(filename, "rb") as file:

        signature = file.read(12)

    valid_image = (
        signature.startswith(b"\xff\xd8\xff")
        or signature.startswith(
            b"\x89PNG\r\n\x1a\n"
        )
        or signature.startswith(b"GIF87a")
        or signature.startswith(b"GIF89a")
        or (
            signature.startswith(b"RIFF")
            and signature[8:12] == b"WEBP"
        )
    )

    if not valid_image:

        os.remove(filename)

        raise ValueError(
            "Файли гирифташуда акси дуруст нест."
        )

    return [
        (filename, "photo")
    ]


# =====================================
# FACEBOOK DOWNLOADER
# =====================================

def download_facebook(url, folder):

    if not re.search(
        r"(facebook\.com|fb\.watch)",
        url,
        re.IGNORECASE
    ):
        raise ValueError(
            "Пайванди Facebook нодуруст аст."
        )

    # Аввал видео

    try:

        return download_with_ytdlp(
            url,
            folder,
            "facebook"
        )

    except Exception as video_error:

        logger.info(
            "Facebook video failed: %s",
            video_error
        )

        # Баъд акс

        try:

            return download_facebook_photo(
                url,
                folder
            )

        except Exception as photo_error:

            raise ValueError(
                "Facebook зеркашӣ нашуд.\n"
                f"Видео: {str(video_error)[:250]}\n"
                f"Акс: {str(photo_error)[:250]}"
            )


# =====================================
# AUTOMATIC PLATFORM DETECTION
# =====================================

def download_media(url, folder):

    url = url.strip()

    if "instagram.com" in url.lower():

        return download_instagram(
            url,
            folder
        )

    elif (
        "youtube.com" in url.lower()
        or "youtu.be" in url.lower()
    ):

        return download_youtube(
            url,
            folder
        )

    elif "tiktok.com" in url.lower():

        return download_tiktok(
            url,
            folder
        )

    elif (
        "facebook.com" in url.lower()
        or "fb.watch" in url.lower()
    ):

        return download_facebook(
            url,
            folder
        )

    else:

        raise ValueError(
            "Ин платформа дастгирӣ намешавад."
        )


# =====================================
# START COMMAND
# =====================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 Салом! Ба TurboSave Bot хуш омадед.\n\n"
        "🔗 Пайванди видеоро ё аксро фиристед.\n\n"
        "Платформаҳои дастгиришаванда:\n"
        "📸 Instagram\n"
        "▶️ YouTube\n"
        "🎵 TikTok\n"
        "📘 Facebook\n\n"
        "Пайвандро фиристед ва интизор шавед."
    )


# =====================================
# SEND DOWNLOADED FILE
# =====================================

async def send_media_file(
    update,
    filename,
    media_type
):

    size = os.path.getsize(filename)

    if size > MAX_SIZE:

        await update.message.reply_text(
            "❌ Ҳаҷми файл аз ҳадди иҷозатдодашудаи бот зиёд аст."
        )

        return

    with open(filename, "rb") as file:

        if media_type == "video":

            await update.message.reply_video(
                video=file,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30
            )

        else:

            try:

                await update.message.reply_photo(
                    photo=file,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30
                )

            except Exception:

                file.seek(0)

                await update.message.reply_document(
                    document=file,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30
                )


# =====================================
# HANDLE USER LINKS
# =====================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    match = re.search(
        r"https?://[^\s<>]+",
        text,
        re.IGNORECASE
    )

    if not match:

        await update.message.reply_text(
            "🔗 Лутфан пайванди Instagram, YouTube, TikTok ё Facebook-ро фиристед."
        )

        return

    url = match.group(0).rstrip(
        ".,!?;:)]}"
    )

    status = await update.message.reply_text(
        "⏳ Пайванд қабул шуд.\n"
        "Зеркашӣ оғоз гардид..."
    )

    folder = tempfile.mkdtemp(
        prefix="turbosave_"
    )

    try:

        results = await asyncio.to_thread(
            download_media,
            url,
            folder
        )

        if not results:

            raise ValueError(
                "Ягон файл зеркашӣ нашуд."
            )

        await status.edit_text(
            f"✅ Зеркашӣ анҷом ёфт!\n"
            f"📁 Шумораи файлҳо: {len(results)}\n"
            f"📤 Фиристодани файлҳо..."
        )

        sent = 0

        for filename, media_type in results:

            if not os.path.exists(filename):
                continue

            try:

                await send_media_file(
                    update,
                    filename,
                    media_type
                )

                sent += 1

            except Exception as error:

                logger.exception(
                    "File sending error"
                )

                await update.message.reply_text(
                    "❌ Фиристодани файл иҷро нашуд: "
                    f"{str(error)[:300]}"
                )

        await status.edit_text(
            f"✅ Кор анҷом ёфт!\n"
            f"📤 Файлҳои фиристодашуда: {sent}"
        )

    except Exception as error:

        logger.exception(
            "Download error"
        )

        await status.edit_text(
            "❌ Боргирӣ иҷро нашуд.\n\n"
            f"Сабаб: {str(error)[:700]}"
        )

    finally:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )


# =====================================
# ERROR HANDLER
# =====================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Telegram error: %s",
        context.error
    )


# =====================================
# MAIN BOT
# =====================================

def main():

    app = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_error_handler(
        error_handler
    )

    logger.info(
        "TurboSave Bot started successfully."
    )

    app.run_polling(
        drop_pending_updates=False
    )


if __name__ == "__main__":

    main()
