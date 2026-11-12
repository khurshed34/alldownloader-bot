
import os
import re
import requests
import yt_dlp
import instaloader

# =====================================
# DOWNLOAD FILE
# =====================================

def download_file(url, filename):

    response = requests.get(
        url,
        stream=True,
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    with open(filename, "wb") as file:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                file.write(chunk)


# =====================================
# INSTAGRAM DOWNLOADER
# =====================================

def download_instagram(url, folder):

    os.makedirs(folder, exist_ok=True)

    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
        url
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

            download_file(media_url, filename)

            results.append((filename, media_type))

        return results

    if not post.is_video:

        filename = os.path.join(
            folder,
            "instagram_photo.jpg"
        )

        download_file(post.url, filename)

        return [(filename, "photo")]

    filename = os.path.join(
        folder,
        "instagram_video.mp4"
    )

    download_file(post.video_url, filename)

    return [(filename, "video")]


# =====================================
# YOUTUBE DOWNLOADER
# =====================================

def download_youtube(url, folder):

    os.makedirs(folder, exist_ok=True)

    if not re.search(
        r"(youtube\.com|youtu\.be)",
        url,
        re.IGNORECASE
    ):
        raise ValueError("Пайванди YouTube нодуруст аст.")

    output = os.path.join(
        folder,
        "youtube_%(id)s.%(ext)s"
    )

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output,
        "quiet": True,
        "noplaylist": True,
        "merge_output_format": "mp4"
    }

    with yt_dlp.YoutubeDL(options) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        filename = ydl.prepare_filename(info)

    if not os.path.exists(filename):
        filename = os.path.splitext(filename)[0] + ".mp4"

    if not os.path.exists(filename):
        raise ValueError("Видеои YouTube зеркашӣ нашуд.")

    return [(filename, "video")]


# =====================================
# TIKTOK DOWNLOADER
# =====================================

def download_tiktok(url, folder):

    os.makedirs(folder, exist_ok=True)

    if "tiktok.com" not in url.lower():
        raise ValueError("Пайванди TikTok нодуруст аст.")

    output = os.path.join(
        folder,
        "tiktok_%(id)s.%(ext)s"
    )

    options = {
        "format": "best",
        "outtmpl": output,
        "quiet": True,
        "noplaylist": True
    }

    with yt_dlp.YoutubeDL(options) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        filename = ydl.prepare_filename(info)

    if not os.path.exists(filename):
        raise ValueError("Видеои TikTok зеркашӣ нашуд.")

    return [(filename, "video")]


# =====================================
# FACEBOOK DOWNLOADER
# =====================================

def download_facebook(url, folder):

    os.makedirs(folder, exist_ok=True)

    if not re.search(
        r"(facebook\.com|fb\.watch)",
        url,
        re.IGNORECASE
    ):
        raise ValueError("Пайванди Facebook нодуруст аст.")

    output = os.path.join(
        folder,
        "facebook_%(id)s.%(ext)s"
    )

    options = {
        "format": "best",
        "outtmpl": output,
        "quiet": True,
        "noplaylist": True
    }

    with yt_dlp.YoutubeDL(options) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        filename = ydl.prepare_filename(info)

    if not os.path.exists(filename):
        raise ValueError("Видеои Facebook зеркашӣ нашуд.")

    return [(filename, "video")]


# =====================================
# AUTOMATIC PLATFORM DETECTION
# =====================================

def download_media(url, folder):

    url = url.strip()

    if "instagram.com" in url.lower():
        return download_instagram(url, folder)

    elif "youtube.com" in url.lower() or "youtu.be" in url.lower():
        return download_youtube(url, folder)

    elif "tiktok.com" in url.lower():
        return download_tiktok(url, folder)

    elif "facebook.com" in url.lower() or "fb.watch" in url.lower():
        return download_facebook(url, folder)

    else:
        raise ValueError("Ин платформа дастгирӣ намешавад.")
