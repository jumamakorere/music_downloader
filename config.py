from pathlib import Path

BASE_URLS = [
    "https://djmwanga.com/category/audio",
    "https://djmwanga.com/category/video",
]

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
LOG_DIR = BASE_DIR / "logs"
DATABASE_DIR = BASE_DIR / "database"

DB_FILE = DATABASE_DIR / "downloads.db"

DOWNLOAD_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)

USER_AGENT = "Mozilla/5.0"