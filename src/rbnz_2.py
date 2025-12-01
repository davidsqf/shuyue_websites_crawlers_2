#!/usr/bin/env python3
"""
rbnz_scrape.py
Fetches (title, url, published_date) from
  1. https://www.rbnz.govt.nz/news-and-events/news
  2. https://www.rbnz.govt.nz/research-and-publications/publications/publications-library
and writes them to  rbnz_articles_YYYYMMDD_HHMMSS.csv
"""

import csv
import datetime as dt
from pathlib import Path
from typing import List, Tuple

from playwright.sync_api import sync_playwright


# ---------- helpers ----------------------------------------------------------


def _extract_from_page(page_url: str,
                       item_selector: str = "article, div.search-result, div.result",
                       title_sel: str = "h3, h2, a",
                       date_sel: str = "time, .published-date, .result-date") -> List[Tuple[str, str, str]]:
    """
    Loads the page with a real browser, waits for the JS-generated list to appear,
    then harvests title / href / date from every result card.

    Returns a list of (title, absolute_url, date_string)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/119.0 Safari/537.36"))
        page.goto(page_url, wait_until="networkidle", timeout=60_000)

        # the page loads results asynchronously; wait for at least one card
        page.wait_for_selector(item_selector, timeout=30_000)

        results = []
        for item in page.query_selector_all(item_selector):
            # ----- title -----
            title_node = item.query_selector(title_sel)
            if not title_node:
                continue
            title = title_node.inner_text().strip()

            # ----- url -----
            link = title_node.get_attribute("href") or ""
            link = link.strip()
            if link and link.startswith("/"):
                link = "https://www.rbnz.govt.nz" + link

            # ----- date -----
            date_node = item.query_selector(date_sel)
            pub_date = (date_node.inner_text().strip()
                        if date_node else "")

            results.append((title, link, pub_date))

        browser.close()
        return results


def scrape_rbnz() -> List[Tuple[str, str, str]]:
    """Scrape both pages and return merged list (deduplicated)."""
    pages = [
        "https://www.rbnz.govt.nz/news-and-events/news"
        "?sort=@computedz95xpublisheddate%20descending",
        "https://www.rbnz.govt.nz/research-and-publications/publications/publications-library"
        "?sort=@computedsortdate%20descending&f:@hierarchicalz95xsz120xacontenttypetagnames=[Publication]",
    ]

    seen = set()
    merged: List[Tuple[str, str, str]] = []

    for url in pages:
        for title, link, date in _extract_from_page(url):
            key = (title, link)          # title+URL is unique enough
            if key not in seen:
                merged.append((title, link, date))
                seen.add(key)

    return merged


def main() -> None:
    rows = scrape_rbnz()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(f"rbnz_articles_{stamp}.csv")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "url", "published_date"])
        writer.writerows(rows)

    print(f"Wrote {len(rows)} records → {out_path.resolve()}")


if __name__ == "__main__":
    main()
