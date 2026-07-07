from datetime import datetime
from pathlib import Path

from config import LOG_DIR
from database import init_db, is_downloaded, save_download
from scraper import get_latest_posts, find_real_media_url
from downloader import create_run_folder, download_direct_file


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


def write_log(message):
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

    print(message)


def save_sources_file(audio_folder, video_folder, downloads):
    audio_source_file = audio_folder / "sources.txt"
    video_source_file = video_folder / "sources.txt"

    with open(audio_source_file, "w", encoding="utf-8") as af, \
         open(video_source_file, "w", encoding="utf-8") as vf:

        for item in downloads:
            text = (
                f"TITLE: {item['title']}\n"
                f"POST URL: {item['post_url']}\n"
                f"MEDIA URL: {item['media_url']}\n"
                f"FILE: {item['file_path']}\n"
                + "-" * 80
                + "\n"
            )

            suffix = Path(item["file_path"]).suffix.lower()

            if suffix in VIDEO_EXTENSIONS:
                vf.write(text)
            else:
                af.write(text)


def main():
    init_db()

    write_log("Checking for new songs/videos...")

    posts = get_latest_posts()

    if not posts:
        write_log("No posts found.")
        return

    run_folder = None
    audio_folder = None
    video_folder = None

    downloaded_sources = []
    new_count = 0

    for post in posts:
        title = post["title"]
        post_url = post["url"]

        if is_downloaded(post_url):
            continue

        try:
            write_log(f"New item found: {title}")
            write_log(f"Post URL: {post_url}")

            media_url = find_real_media_url(post_url)

            if not media_url:
                raise Exception("No direct MP3/MP4 link found inside post page.")

            if run_folder is None:
                run_folder, audio_folder, video_folder = create_run_folder()
                write_log(f"Download folder: {run_folder}")
                write_log(f"Audio folder: {audio_folder}")
                write_log(f"Video folder: {video_folder}")

            write_log(f"Media URL: {media_url}")

            file_path = download_direct_file(
                media_url=media_url,
                title=title,
                audio_folder=audio_folder,
                video_folder=video_folder,
            )

            save_download(
                title=title,
                url=post_url,
                media_url=media_url,
                status="success",
                file_path=file_path,
                folder_path=run_folder,
            )

            downloaded_sources.append({
                "title": title,
                "post_url": post_url,
                "media_url": media_url,
                "file_path": str(file_path),
            })

            new_count += 1

            write_log(f"Downloaded successfully: {file_path}")

        except Exception as e:
            save_download(
                title=title,
                url=post_url,
                status="failed",
                error_message=str(e),
            )

            write_log(f"Download failed: {title}")
            write_log(str(e))

    if run_folder and downloaded_sources:
        save_sources_file(
            audio_folder=audio_folder,
            video_folder=video_folder,
            downloads=downloaded_sources,
        )

    if new_count == 0:
        write_log("No new songs/videos found.")
    else:
        write_log(f"Total new downloads: {new_count}")

    write_log("Check completed.")


if __name__ == "__main__":
    main()