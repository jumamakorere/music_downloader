import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from config import BASE_URLS, USER_AGENT


def clean_title(title):
    title = re.sub(r'[\\/*?:"<>|]', "", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def get_latest_posts():
    posts = []
    seen_urls = set()

    headers = {
        "User-Agent": USER_AGENT
    }

    for page_url in BASE_URLS:
        try:
            response = requests.get(page_url, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to open {page_url}: {e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        for link in soup.find_all("a", href=True):
            title = clean_title(link.get_text(" ", strip=True))
            href = link["href"]

            if not title:
                continue

            full_url = urljoin(page_url, href)

            if "/category/" in full_url:
                continue

            if "djmwanga.com/" not in full_url:
                continue

            if full_url in seen_urls:
                continue

            title_upper = title.upper()

            if (
                "AUDIO" in title_upper
                or "VIDEO" in title_upper
                or "DOWNLOAD" in title_upper
            ):
                posts.append({
                    "title": title,
                    "url": full_url
                })

                seen_urls.add(full_url)

    return posts


def find_real_media_url(post_url):
    headers = {
        "User-Agent": USER_AGENT
    }

    response = requests.get(post_url, headers=headers, timeout=30)
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    media_extensions = (
        ".mp3",
        ".mp4",
        ".m4a",
        ".webm",
        ".wav",
        ".aac"
    )

    for tag in soup.find_all(["a", "audio", "source", "video"]):
        src = tag.get("href") or tag.get("src")

        if not src:
            continue

        src = urljoin(post_url, src)

        if src.lower().split("?")[0].endswith(media_extensions):
            return src

    match = re.search(
        r'https?://[^\s"\']+\.(mp3|mp4|m4a|webm|wav|aac)(\?[^\s"\']*)?',
        html,
        re.IGNORECASE
    )

    if match:
        return match.group(0)

    return None