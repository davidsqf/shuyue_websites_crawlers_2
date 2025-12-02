#!/usr/bin/env python3
"""
Fetch latest 100 RBA news items from https://www.rba.gov.au/news/

Output:
  - Prints:  date <TAB> title <TAB> url
  - Writes:  rba_news_latest_100.csv  (columns: title, url, date)
"""

from __future__ import annotations

import csv
import re
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


def looks_like_date(text: str) -> bool:
    """
    Heuristic to detect date lines like:
      '2 December 2025 2.30 pm AEDT'
    """
    if not any(m in text for m in MONTH_NAMES):
        return False
    if not re.search(r"\b20\d{2}\b", text):
        return False
    return True


def fetch_news_page() -> str:
    resp = requests.get(NEWS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_news(html: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Parse the RBA /news/ page HTML and extract up to `limit` articles.

    Each article is roughly:
        <h4><a href="...">Title</a></h4>
        [0 or more description / label elements]
        <p>2 December 2025 2.30 pm AEDT</p>

    We:
      - Take all <h4> in the main content
      - For each <h4>, get the link text & href
      - Walk forwards through siblings until we find a line that "looks like a date"
    """
    soup = BeautifulSoup(html, "lxml")

    main = soup.find("main")
    if main is None:
        # Fallback if the structure ever changes
        main = soup

    results: List[Dict[str, Any]] = []

    for h4 in main.find_all("h4"):
        if not isinstance(h4, Tag):
            continue

        a = h4.find("a", href=True)
        if a is None:
            # Some h4s might be non-article headings; skip them
            continue

        title = " ".join(a.stripped_strings)
        href = a["href"]
        url = urljoin(BASE_URL, href)

        # Find the first following sibling that looks like a date
        date_text = ""
        for sib in h4.next_siblings:
            if isinstance(sib, NavigableString):
                # Skip whitespace
                continue

            if isinstance(sib, Tag):
                # If we've hit the next heading, we've gone too far
                if sib.name in {"h3", "h4"}:
                    break

                text = " ".join(sib.stripped_strings)
                if not text:
                    continue

                if looks_like_date(text):
                    date_text = text
                    break

        results.append(
            {
                "title": title,
                "url": url,
                "date": date_text,
            }
        )

        if len(results) >= limit:
            break

    return results


def save_to_csv(rows: List[Dict[str, Any]], path: str = "rba_news_latest_100.csv") -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "url", "date"])
        for row in rows:
            writer.writerow([row["title"], row["url"], row["date"]])


def main() -> None:
    html = fetch_news_page()
    articles = parse_news(html, limit=10)

    for art in articles:
        print(f"{art['date']}\t{art['title']}\t{art['url']}")

    print(f"\nTotal articles fetched: {len(articles)}")

    save_to_csv(articles)
    print("Saved to rba_news_latest_100.csv")


if __name__ == "__main__":
    main()
