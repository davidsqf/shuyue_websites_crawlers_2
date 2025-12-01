#!/usr/bin/env python3
"""
rbnz_collect.py
Scrapes (title, url, published_date) from

  1) https://www.rbnz.govt.nz/news-and-events/news
  2) https://www.rbnz.govt.nz/research-and-publications/publications/publications-library

and writes them to rbnz_articles_YYYYMMDD_HHMMSS.csv
"""

import csv
import datetime as dt
import re
import time
from pathlib import Path
from typing import List, Tuple

from playwright.sync_api import sync_playwright


# -----------------------------------------------------------------------------
# utility helpers
# -----------------------------------------------------------------------------

ISO_OUT_FMT = "%Y-%m-%d"          # final human-readable format


def _clean_date(raw: str) -> str:
    """
    Accepts things like
        • 'Published date 04 November, 2025'
        • '04 November 2025'
        • '2025-11-04'
    Returns ISO '2025-11-04'.

    Falls back to '' if no date could be parsed.
    """
    raw = raw.strip()
    # throw away leading text
    raw = re.sub(r'Published date', '', raw, flags=re.I).strip(", :")
    # unify comma
    raw = raw.replace(",", "")
    try:
        for fmt in ("%d %B %Y", "%d %B %Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(raw, fmt).strftime(ISO_OUT_FMT)
            except ValueError:
                continue
    except Exception:
        pass
    return ""


def _scroll_to_bottom(page, pause_ms: int = 800) -> None:
    """Simple ‘infinite-scroll’: keeps paging until height no longer grows."""
    last_height = -1
    while True:
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(pause_ms)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def _extract_from_page(
    page_url: str,
    item_selector: str = "article, div.search-result, div.result"
) -> List[Tuple[str, str, str]]:
    """
    Uses a real Chromium browser to load the page,
    scrolls to the bottom so lazy-loads finish,
    then extracts (title, url, iso_date) from every card.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/119 Safari/537.36"))
        print(f"Fetching {page_url} …")
        page.goto(page_url, wait_until="networkidle", timeout=60_000)

        # make sure JS finished adding cards
        page.wait_for_selector(item_selector, timeout=30_000)

        # handle infinite scroll (both pages use it)
        _scroll_to_bottom(page)

        results = []
        for card in page.query_selector_all(item_selector):
            # ---------------- title & link ----------------
            title_node = card.query_selector("h3 a, h2 a, a")
            if not title_node:
                continue
            title = title_node.inner_text().strip()
            href = (title_node.get_attribute("href") or "").strip()
            if href.startswith("/"):
                href = f"https://www.rbnz.govt.nz{href}"

            # ---------------- date ----------------
            date_node = card.query_selector("time, .published-date, .result-date")
            date_text = date_node.inner_text().strip() if date_node else ""
            iso_date = _clean_date(date_text)

            results.append((title, href, iso_date))

        browser.close()
        return results


def scrape() -> List[Tuple[str, str, str]]:
    pages = [
        ("news",
         "https://www.rbnz.govt.nz/news-and-events/news"
         "?sort=@computedz95xpublisheddate%20descending"),
        ("publications",
         "https://www.rbnz.govt.nz/research-and-publications/publications/publications-library"
         "?sort=@computedsortdate%20descending&"
         "f:@hierarchicalz95xsz120xacontenttypetagnames=[Publication]"),
    ]

    merged, seen = [], set()
    for label, url in pages:
        try:
            for title, link, date in _extract_from_page(url):
                key = (title, link)
                if key not in seen:
                    merged.append((title, link, date))
                    seen.add(key)
        except Exception as exc:               # robust: still return what we got
            print(f"⚠️  Error fetching {label}: {exc}")

    return merged


# -----------------------------------------------------------------------------
# main entry
# -----------------------------------------------------------------------------

def main() -> None:
    rows = scrape()
    now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(f"rbnz_articles_{now}.csv")

    # write CSV
    with out_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "url", "published_date"])
        writer.writerows(rows)

    # pretty console output
    print(f"\n--- {len(rows)} total records ---")
    for t, u, d in rows[:10]:           # show first 10 for brevity
        print(f"{d:<12}  {t}")
        print(f"   {u}")

    print(f"\n✅  Saved → {out_file.resolve()}")


if __name__ == "__main__":
    main()
