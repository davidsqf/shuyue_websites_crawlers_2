import csv
import re
import time
import random
from datetime import datetime
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from logging_utils import setup_logger
from paths import APRA_RESULTS

BASE_URL = "https://www.apra.gov.au"
LIST_URL = "https://www.apra.gov.au/news-and-publications/39"

# Matches things like "Friday 28 November 2025" or "28 November 2025"
DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*\d{1,2}\s+[A-Za-z]+\s+\d{4}"
)

logger = setup_logger("APRA")

# "Human-like" crawling parameters (tune as you like)
MIN_DELAY = 1.0   # minimum delay between requests (seconds)
MAX_DELAY = 3.0   # maximum delay between requests (seconds)
MAX_RETRIES = 3   # number of attempts per URL
BACKOFF_BASE = 1.5  # exponential backoff base


def human_delay():
    """
    Sleep for a random amount of time between MIN_DELAY and MAX_DELAY
    to mimic human browsing behaviour.
    """
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    logger.debug("Sleeping for %.2f seconds before next request", delay)
    time.sleep(delay)


def fetch_with_retries(session: requests.Session, url: str, timeout: int = 30) -> requests.Response:
    """
    Fetch a URL with a few retries and jittered backoff, while inserting
    small random delays to appear more human-like.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        # Human-like pause before each attempt
        human_delay()
        try:
            logger.debug("GET %s (attempt %d/%d)", url, attempt, MAX_RETRIES)
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Attempt %d/%d failed for %s: %s",
                attempt,
                MAX_RETRIES,
                url,
                exc,
            )
            if attempt < MAX_RETRIES:
                backoff = (BACKOFF_BASE ** attempt) + random.uniform(0, 0.5)
                logger.debug("Backing off for %.2f seconds before retrying %s", backoff, url)
                time.sleep(backoff)

    logger.error("All %d attempts failed for %s: %s", MAX_RETRIES, url, last_exc)
    # Let the caller decide how to handle the failure
    raise last_exc


def get_session() -> requests.Session:
    """Create a session with a realistic User-Agent and common headers."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
                "Gecko/20100101 Firefox/125.0"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "DNT": "1",
            # Let requests handle gzip/deflate by default; we don't need to force it
        }
    )
    return s


def extract_article_links(html: str):
    """
    From the listing page HTML, return a list of (title, url) tuples
    for article links.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        # Normalise relative URLs to absolute
        url = urljoin(BASE_URL, href)
        parsed = urlparse(url)
        path = parsed.path

        # Only keep clean article URLs like /news-and-publications/some-slug
        if not path.startswith("/news-and-publications/"):
            continue
        if "?" in parsed.query or "?" in url or "#" in url:
            # Skip filter/pagination/tab links
            continue

        title = a.get_text(strip=True)
        if not title:
            continue

        if url in seen:
            continue

        seen.add(url)
        links.append((title, url))

    return links


def extract_date_from_article(html: str) -> str:
    """Try to pull a human-readable date from an article page."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Prefer an explicit <time> tag if present
    time_tag = soup.find("time")
    if time_tag:
        text = time_tag.get_text(strip=True)
        if text:
            return text

    # 2. Fallback: regex over the full text content
    text = " ".join(soup.get_text(separator=" ").split())
    m = DATE_RE.search(text)
    if m:
        return m.group(0)

    return ""


def normalize_date_to_iso(date_str: str) -> str:
    """
    Convert a human-readable date like 'Friday 28 November 2025'
    or '28 November 2025' to 'YYYY-MM-DD'. Returns '' on failure.
    """
    if not date_str:
        return ""

    date_str = " ".join(date_str.split())  # normalize spaces

    # Try with weekday first, then without
    for fmt in ("%A %d %B %Y", "%d %B %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # If parsing fails, return empty string (keep CSV structure simple)
    return ""


def scrape_apra(save: bool = True) -> List[Tuple[str, str, str]]:
    """
    Crawl the APRA news listings and return a list of
    (iso_date, title, url) tuples. When `save` is True, the results
    overwrite the APRA_RESULTS CSV file.
    """
    session = get_session()

    logger.info("Fetching listing page %s", LIST_URL)
    try:
        resp = fetch_with_retries(session, LIST_URL, timeout=30)
    except requests.RequestException as exc:
        logger.error("Failed to fetch listing page: %s", exc)
        return []

    article_links = extract_article_links(resp.text)
    logger.info("Found %d candidate article links", len(article_links))

    if not article_links:
        logger.warning("No article links were found on the listing page.")
        return []

    rows: List[Tuple[str, str, str]] = []

    for idx, (title, url) in enumerate(article_links, start=1):
        logger.info("(%d/%d) Fetching article: %s", idx, len(article_links), url)
        try:
            r = fetch_with_retries(session, url, timeout=30)
            raw_date = extract_date_from_article(r.text)
            iso_date = normalize_date_to_iso(raw_date)
        except requests.RequestException as exc:
            logger.error("Failed to fetch article %s: %s", url, exc)
            raw_date = ""
            iso_date = ""

        rows.append((iso_date, title, url))
        logger.debug("%s | %s | %s", iso_date, title, url)

    if save:
        with open(APRA_RESULTS, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        logger.info("Saved %d articles to %s", len(rows), APRA_RESULTS)

    return rows


def main():
    scrape_apra(save=True)


if __name__ == "__main__":
    main()
