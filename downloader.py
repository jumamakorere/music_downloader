import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from config import DOWNLOAD_DIR, USER_AGENT


VIDEO_EXTENSIONS = [
    ".mp4",
    ".avi",
    ".mkv",
    ".mov",
    ".webm",
    ".flv",
    ".wmv",
    ".mpeg",
    ".3gp",
]


def safe_filename(name):
    # Remove AUDIO or VIDEO at the beginning
    name = re.sub(r"^(AUDIO|VIDEO)\s+", "", name, flags=re.IGNORECASE)

    # Remove Download at the end
    name = re.sub(r"\s+DOWNLOAD$", "", name, flags=re.IGNORECASE)

    # Replace long dash with normal dash
    name = name.replace("–", "-")

    # Remove illegal Windows filename characters
    name = re.sub(r'[\\/*?:"<>|]', "", name)

    # Replace multiple spaces with one
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def create_run_folder():
    now = datetime.now()

    root = (
        DOWNLOAD_DIR
        / str(now.year)
        / now.strftime("%Y-%m-%d_%H-%M-%S")
    )

    audio_folder = root / "Audio"
    video_folder = root / "Video"

    audio_folder.mkdir(parents=True, exist_ok=True)
    video_folder.mkdir(parents=True, exist_ok=True)

    return root, audio_folder, video_folder


def get_extension(media_url):
    path = urlparse(media_url).path
    ext = Path(path).suffix.lower()

    if ext:
        return ext

    return ".mp3"


def is_video(ext):
    return ext.lower() in VIDEO_EXTENSIONS


def download_direct_file(media_url, title, audio_folder, video_folder):
    headers = {
        "User-Agent": USER_AGENT
    }

    ext = get_extension(media_url)

    folder = video_folder if is_video(ext) else audio_folder

    clean_title = safe_filename(title)

    filename = clean_title + ext
    file_path = folder / filename

    counter = 1

    while file_path.exists():
        filename = f"{clean_title}_{counter}{ext}"
        file_path = folder / filename
        counter += 1

    with requests.get(
        media_url,
        headers=headers,
        stream=True,
        timeout=120,
    ) as response:
        response.raise_for_status()

        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    return file_path