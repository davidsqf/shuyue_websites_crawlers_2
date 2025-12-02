#!/usr/bin/env python3
"""
Fetch latest 100 RBA news items from https://www.rba.gov.au/news/

Output:
  - Prints lines:  YYYY-MM-DD,title,url
  - Writes file:   rba_news_latest_100.csv (no header line, same format)
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from typing import List, Dict, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

BASE_URL = "https://www.rba.gov.au"
NEWS_URL = f"{BASE_URL}/news/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36"
    )
}

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
)


# --------------------------------------------------------------------------- #
# Date helpers
# --------------------------------------------------------------------------- #

def looks_like_date(text: str) -> bool:
    """
    Detect lines like:
      '2 December 2025 2.30 pm AEDT'
      '31 October 2025 11.30 am AEDT'
    and ignore sentences that just mention 'October 2025' in passing.
    """
    text = text.strip().replace("\xa0", " ")
    if not text:
        return False

    # Must start with day + month
    if not re.match(r"^\d{1,2}\s+[A-Za-z]+", text):
        return False

    # Must contain a 4-digit year starting with 20
    if not re.search(r"\b20\d{2}\b", text):
        return False

    return True


def parse_date_iso(text: str) -> str:
    """
    Given something like '2 December 2025 2.30 pm AEDT',
    return '2025-12-02'.
    """
    text = " ".join(text.replace("\xa0", " ").split())
    m = re.search(r"(\d{1,2}\s+[A-Za-z]+\s+20\d{2})", text)
    if not m:
        return ""

    date_part = m.group(1)  # e.g. '2 December 2025'
    dt = datetime.strptime(date_part, "%d %B %Y")
    return dt.strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# HTML parsing
# --------------------------------------------------------------------------- #

def fetch_news_page() -> str:
    resp = requests.get(NEWS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def find_heading_link(node: NavigableString) -> Tag | None:
    """
    From a date text node, walk backwards through the document and find
    the nearest <a> that lives inside an <h2>/<h3>/<h4> and is *not*
    an 'Audio' or 'Q&A Transcript' auxiliary link.
    """
    curr: Tag | NavigableString = node

    while True:
        a = curr.find_previous("a")
        if a is None:
            return None

        text = " ".join(a.stripped_strings)
        if not text:
            curr = a
            continue

        lower = text.strip().lower()
        # Skip auxiliary links that appear between the main title and date
        if lower in {"audio", "q&a transcript", "download", "subscribe"}:
            curr = a
            continue

        heading = a.find_parent(["h2", "h3", "h4"])
        if not heading:
            curr = a
            continue

        return a


def parse_news(html: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Parse the RBA /news/ HTML and extract up to `limit` items.

    Strategy:
      - Walk all text nodes in the main content area.
      - For any text node that looks like a date, find the nearest
        preceding heading link (in an <h2>/<h3>/<h4>).
      - Use that link as the article title + URL.
    """
    soup = BeautifulSoup(html, "lxml")

    content = (
        soup.find("main")
        or soup.find(id="content")
        or soup.body
        or soup
    )

    results: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for text_node in content.find_all(string=True):
        if not isinstance(text_node, NavigableString):
            continue

        raw = str(text_node)
        t = " ".join(raw.replace("\xa0", " ").split())
        if not looks_like_date(t):
            continue

        iso_date = parse_date_iso(t)
        if not iso_date:
            # If parsing somehow fails, skip this one
            continue

        link = find_heading_link(text_node)
        if link is None:
            continue

        href = link.get("href")
        if not href:
            continue

        title = " ".join(link.stripped_strings)
        url = urljoin(BASE_URL, href)

        key = (iso_date, title, url)
        if key in seen:
            continue
        seen.add(key)

        results.append(
            {
                "date": iso_date,
                "title": title,
                "url": url,
            }
        )

        if len(results) >= limit:
            break

    return results


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def save_to_csv(rows: List[Dict[str, Any]], path: str = "rba_news_latest_100.csv") -> None:
    """
    Write rows to CSV with NO header line, in the order:
      date,title,url
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow([row["date"], row["title"], row["url"]])


def main() -> None:
    html = fetch_news_page()
    articles = parse_news(html, limit=100)

    # Print each line as: YYYY-MM-DD,title,url
    for art in articles:
        # This is intentionally plain string formatting, not csv.writer,
        # so you'll see exactly the format you requested in stdout.
        print(f"{art['date']},{art['title']},{art['url']}")

    print(f"\nTotal articles fetched: {len(articles)}")

    save_to_csv(articles)
    print("Saved to rba_news_latest_100.csv (no header line).")


if __name__ == "__main__":
    main()
