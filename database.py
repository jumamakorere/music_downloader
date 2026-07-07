import sqlite3
from datetime import datetime
from config import DB_FILE


def get_connection():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT UNIQUE,
            media_url TEXT,
            status TEXT,
            file_path TEXT,
            folder_path TEXT,
            error_message TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def is_downloaded(url):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM downloads WHERE url = ? AND status = 'success'",
        (url,)
    )

    result = cursor.fetchone()
    conn.close()

    return result is not None


def save_download(
    title,
    url,
    media_url=None,
    status="success",
    file_path=None,
    folder_path=None,
    error_message=None
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO downloads
        (
            title,
            url,
            media_url,
            status,
            file_path,
            folder_path,
            error_message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
        url,
        media_url,
        status,
        str(file_path) if file_path else None,
        str(folder_path) if folder_path else None,
        error_message,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()