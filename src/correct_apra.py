import csv
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.apra.gov.au"
LIST_URL = "https://www.apra.gov.au/news-and-publications/39"
RESULTS_CSV = "results.csv"

# Matches things like "Friday 28 November 2025" or "28 November 2025"
DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*\d{1,2}\s+[A-Za-z]+\s+\d{4}"
)


def get_session() -> requests.Session:
    """Create a session with a realistic User-Agent."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
                "Gecko/20100101 Firefox/125.0"
            ),
            "Accept-Language": "en",
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


def main():
    session = get_session()

    # Fetch the listing page
    resp = session.get(LIST_URL, timeout=30)
    resp.raise_for_status()

    article_links = extract_article_links(resp.text)

    if not article_links:
        print("No article links were found on the listing page.")
        return

    rows = []

    for title, url in article_links:
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            raw_date = extract_date_from_article(r.text)
            iso_date = normalize_date_to_iso(raw_date)
        except requests.RequestException as e:
            print(f"Failed to fetch article {url}: {e}")
            raw_date = ""
            iso_date = ""

        rows.append((iso_date, title, url))

        # Echo to stdout so you can see progress/results
        print(f"{iso_date} | {title} | {url}")

    # Append results to CSV (no header, so you can aggregate from many runs)
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"\nAppended {len(rows)} articles to {RESULTS_CSV}")


if __name__ == "__main__":
    main()
