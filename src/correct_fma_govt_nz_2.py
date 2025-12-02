import csv
import time
import random
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from logging_utils import setup_logger

RESULTS_CSV = "results.csv"
logger = setup_logger("FMA")


def normalize_date_to_iso(date_str: str) -> str:
    """
    Convert a human-readable date like '28 November 2025'
    (or similar) to 'YYYY-MM-DD'. Returns '' on failure.
    """
    if not date_str:
        return ""

    date_str = " ".join(date_str.split())  # normalize spaces

    # Try a few common formats
    formats = [
        "%d %B %Y",    # 28 November 2025
        "%d %b %Y",    # 28 Nov 2025
        "%A %d %B %Y", # Friday 28 November 2025
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # If parsing fails, return empty string
    return ""


def get_session() -> requests.Session:
    """
    Create a session that looks more like a real browser.
    """
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/118.0.5993.88 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-NZ,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
    )
    return s


def human_delay(page_num: int) -> None:
    """
    Sleep for a random 'think time' to look more human.

    - Short random pause between every page.
    - Occasionally a slightly longer pause every few pages.
    """
    base = random.uniform(0.1, 1.0)  # normal think time
    extra = 0.0

    # Every 5 pages, pretend we took a slightly longer break
    if page_num > 0 and page_num % 5 == 0:
        extra = random.uniform(0.1, 1.0)

    delay = base + extra
    logger.info("Sleeping for %.2f seconds before fetching next page", delay)
    time.sleep(delay)


def fetch_media_releases():
    base_url = "https://www.fma.govt.nz"
    url = "https://www.fma.govt.nz/news/all-releases/media-releases/"

    session = get_session()
    releases = []
    visited_urls = set()
    page_num = 0

    while True:
        if url in visited_urls:
            logger.warning("Loop detected, stopping at %s", url)
            break

        visited_urls.add(url)
        page_num += 1

        # Human-like delay before each request
        human_delay(page_num)

        logger.info("Fetching page %d: %s", page_num, url)
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract each article entry (business logic unchanged)
        for item in soup.find_all("li", class_="search-results-semantic__result-item"):
            h3 = item.find("h3")
            a = h3.find("a") if h3 else None
            title = a.get_text(strip=True) if a else None
            article_url = urljoin(base_url, a["href"]) if a else None

            date_tag = item.find("span", class_="search-results-semantic__date")
            date_text = date_tag.get_text(strip=True) if date_tag else None

            if title and article_url and date_text:
                releases.append(
                    {
                        "title": title,
                        "url": article_url,
                        "date": date_text,
                    }
                )

        # Detect next page (business logic unchanged)
        next_link = soup.find("a", class_="next page-link")
        if not next_link:
            break

        next_href = next_link.get("href")
        if not next_href:
            break

        # Build next URL
        url = urljoin(base_url, next_href)

    return releases


def save_results(releases):
    # Append to a shared results file in (yyyy-mm-dd, title, url) format
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for r in releases:
            iso_date = normalize_date_to_iso(r["date"])
            writer.writerow([iso_date, r["title"], r["url"]])

    logger.info("Appended %d articles to %s", len(releases), RESULTS_CSV)


if __name__ == "__main__":
    logger.info("Starting FMA media releases crawl")
    releases = fetch_media_releases()
    logger.info("Total releases scraped: %d", len(releases))

    # Print first few with normalized dates
    for r in releases[:10]:
        iso_date = normalize_date_to_iso(r["date"])
        logger.debug("%s | %s | %s", iso_date, r["title"], r["url"])

    save_results(releases)
