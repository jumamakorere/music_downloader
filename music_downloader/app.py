from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import urlopen


LOGGER = logging.getLogger("music_downloader")
MEDIA_EXTENSIONS = {
    ".aac": "audio",
    ".flac": "audio",
    ".m4a": "audio",
    ".mp3": "audio",
    ".ogg": "audio",
    ".opus": "audio",
    ".wav": "audio",
    ".webm": "video",
    ".mkv": "video",
    ".mov": "video",
    ".mp4": "video",
    ".mpeg": "video",
    ".mpg": "video",
}
LINK_PATTERN = re.compile(r"""(?:href|src)\s*=\s*["']([^"'#]+)["']""", re.IGNORECASE)
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def configure_logging(level: int = logging.INFO) -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")
    else:
        logging.getLogger().setLevel(level)


def clean_filename(name: str) -> str:
    base = unquote(name).strip()
    base = INVALID_FILENAME_CHARS.sub("_", base)
    base = re.sub(r"\s+", " ", base)
    if "." in base:
        stem, ext = base.rsplit(".", 1)
        stem = stem.strip(" ._") or "download"
        ext = ext.strip(" ._")
        return f"{stem}.{ext}" if ext else stem
    return base.strip(" ._") or "download"


def infer_media_type(url: str, content_type: str | None = None) -> str | None:
    extension = Path(urlparse(url).path).suffix.lower()
    media_type = MEDIA_EXTENSIONS.get(extension)
    if media_type:
        return media_type
    if content_type:
        guessed_type, _ = mimetypes.guess_type(f"file{extension or ''}")
        content_type = content_type.split(";", 1)[0].strip().lower()
        if content_type.startswith("audio/"):
            return "audio"
        if content_type.startswith("video/"):
            return "video"
        if guessed_type:
            if guessed_type.startswith("audio/"):
                return "audio"
            if guessed_type.startswith("video/"):
                return "video"
    return None


def extract_links(html: str, base_url: str) -> list[str]:
    return [urljoin(base_url, match) for match in LINK_PATTERN.findall(html)]


@dataclass(frozen=True)
class SiteConfig:
    name: str
    url: str
    post_patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DownloaderConfig:
    output_root: Path
    database_path: Path
    sites: list[SiteConfig]
    dry_run: bool = False


class DownloadHistory:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    post_url TEXT NOT NULL,
                    media_url TEXT NOT NULL UNIQUE,
                    local_path TEXT NOT NULL,
                    downloaded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_name TEXT NOT NULL,
                    post_url TEXT NOT NULL UNIQUE,
                    checked_at TEXT NOT NULL
                )
                """
            )

    def has_downloaded(self, media_url: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM downloads WHERE media_url = ? LIMIT 1", (media_url,)
            ).fetchone()
        return row is not None

    def has_processed_post(self, post_url: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_posts WHERE post_url = ? LIMIT 1", (post_url,)
            ).fetchone()
        return row is not None

    def record_download(
        self,
        site_name: str,
        post_url: str,
        media_url: str,
        local_path: Path,
        downloaded_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO downloads
                (site_name, post_url, media_url, local_path, downloaded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (site_name, post_url, media_url, str(local_path), downloaded_at),
            )

    def mark_post_processed(self, site_name: str, post_url: str, checked_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO processed_posts (site_name, post_url, checked_at)
                VALUES (?, ?, ?)
                """,
                (site_name, post_url, checked_at),
            )

    def download_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM downloads").fetchone()
        return int(row[0]) if row else 0


class MusicDownloader:
    def __init__(self, config: DownloaderConfig) -> None:
        self.config = config
        self.history = DownloadHistory(config.database_path)
        self.run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self._run_root: Path | None = None

    def run(self) -> dict[str, int]:
        summary = {"posts_checked": 0, "files_downloaded": 0, "files_skipped": 0}
        for site in self.config.sites:
            posts = self._discover_posts(site)
            for post_url in posts:
                if self.history.has_processed_post(post_url):
                    LOGGER.info("Skipping previously processed post: %s", post_url)
                    summary["files_skipped"] += 1
                    continue
                summary["posts_checked"] += 1
                downloaded, skipped = self._process_post(site, post_url)
                summary["files_downloaded"] += downloaded
                summary["files_skipped"] += skipped
                self.history.mark_post_processed(site.name, post_url, self.run_timestamp)
        LOGGER.info("Run summary: %s", summary)
        return summary

    def _discover_posts(self, site: SiteConfig) -> list[str]:
        html = self._fetch_text(site.url)
        links = extract_links(html, site.url)
        direct_media = [link for link in links if infer_media_type(link)]
        if direct_media:
            return [site.url]
        same_page_media = [
            link for link in extract_links(html, site.url) if infer_media_type(link) is not None
        ]
        if same_page_media:
            return [site.url]
        post_urls: list[str] = []
        for link in links:
            if infer_media_type(link):
                continue
            if site.post_patterns and not any(pattern in link for pattern in site.post_patterns):
                continue
            parsed_site = urlparse(site.url)
            parsed_link = urlparse(link)
            if parsed_link.scheme not in {"http", "https", "file"}:
                continue
            if parsed_link.scheme != "file" and parsed_link.netloc != parsed_site.netloc:
                continue
            if link not in post_urls and link != site.url:
                post_urls.append(link)
        return post_urls or [site.url]

    def _process_post(self, site: SiteConfig, post_url: str) -> tuple[int, int]:
        html = self._fetch_text(post_url)
        media_urls = [link for link in extract_links(html, post_url) if infer_media_type(link)]
        downloaded = 0
        skipped = 0
        for media_url in media_urls:
            if self.history.has_downloaded(media_url):
                LOGGER.info("Skipping duplicate media URL: %s", media_url)
                skipped += 1
                continue
            local_path = self._download_media(site, post_url, media_url)
            if local_path is None:
                skipped += 1
                continue
            downloaded += 1
            self.history.record_download(
                site.name, post_url, media_url, local_path, self.run_timestamp
            )
        return downloaded, skipped

    def _download_media(self, site: SiteConfig, post_url: str, media_url: str) -> Path | None:
        media_type = infer_media_type(media_url)
        if media_type is None:
            LOGGER.warning("Unsupported media URL skipped: %s", media_url)
            return None
        filename = clean_filename(os.path.basename(urlparse(media_url).path) or "download")
        destination = self._destination_for(media_type, filename)
        if self.config.dry_run:
            LOGGER.info("[dry-run] Would download %s from %s", media_url, post_url)
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.info("Downloading %s from %s", media_url, site.name)
        with urlopen(media_url) as response, destination.open("wb") as handle:
            handle.write(response.read())
        return destination

    def _destination_for(self, media_type: str, filename: str) -> Path:
        if self._run_root is None:
            self._run_root = self.config.output_root / self.run_timestamp
        folder_name = "Audio" if media_type == "audio" else "Video"
        return self._run_root / folder_name / filename

    @staticmethod
    def _fetch_text(url: str) -> str:
        with urlopen(url) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")


def load_config(path: Path, output_root: Path | None = None, database_path: Path | None = None, dry_run: bool = False) -> DownloaderConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw_config = json.load(handle)
    sites = [
        SiteConfig(
            name=site["name"],
            url=site["url"],
            post_patterns=list(site.get("post_patterns", [])),
        )
        for site in raw_config.get("sites", [])
    ]
    return DownloaderConfig(
        output_root=Path(output_root or raw_config.get("output_root", "downloads")),
        database_path=Path(database_path or raw_config.get("database_path", "downloads/history.sqlite3")),
        sites=sites,
        dry_run=dry_run or bool(raw_config.get("dry_run", False)),
    )


def run_from_config(config_path: Path, output_root: Path | None = None, database_path: Path | None = None, dry_run: bool = False) -> dict[str, int]:
    configure_logging()
    config = load_config(config_path, output_root=output_root, database_path=database_path, dry_run=dry_run)
    downloader = MusicDownloader(config)
    return downloader.run()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download new music and video posts from supported sites.")
    parser.add_argument("config", type=Path, help="Path to a JSON configuration file.")
    parser.add_argument("--output-root", type=Path, help="Optional download output directory.")
    parser.add_argument("--database-path", type=Path, help="Optional SQLite database path.")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without downloading files.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    run_from_config(
        config_path=args.config,
        output_root=args.output_root,
        database_path=args.database_path,
        dry_run=args.dry_run,
    )
    return 0
