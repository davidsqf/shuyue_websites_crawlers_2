#!/usr/bin/env python3
"""
Scrape Reserve Bank of New Zealand (RBNZ) news + publications.

Outputs rbnz_articles_<YYYYMMDD_HHMMSS>.csv
with:  title , url , published_date (YYYY-MM-DD)
"""

import csv
import datetime as dt
import re
import sys
import time
from pathlib import Path
from typing import List, Tuple

from playwright.sync_api import TimeoutError, sync_playwright

ISO_FMT = "%Y-%m-%d"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")


# ───────────────────────── helpers ────────────────────────────────────────────
def _clean_date(raw: str) -> str:
    """Return ISO date (`YYYY-MM-DD`) or empty string."""
    raw = raw.strip().replace(",", "")
    # Epoch?
    if raw.isdigit():
        ts = int(raw)
        if ts > 3_600_000_000:           # millis heuristic
            ts //= 1000
        try:
            return dt.datetime.utcfromtimestamp(ts).strftime(ISO_FMT)
        except (OSError, ValueError):
            pass
    raw = re.sub(r"^Published date", "", raw, flags=re.I).strip()
    for fmt in ("%d %B %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(raw, fmt).strftime(ISO_FMT)
        except ValueError:
            continue
    return ""


def _scroll_to_bottom(page, pause_ms: int = 600):
    """Trigger lazy-loading by scrolling until height stabilises."""
    last = -1
    while True:
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(pause_ms)
        cur = page.evaluate("document.body.scrollHeight")
        if cur == last:
            return
        last = cur


def _extract(page, label: str, url: str,
             item_sel: str = "article, div.search-result, div.result"
             ) -> List[Tuple[str, str, str]]:
    """Open page, wait for cards, harvest (title, url, iso_date)."""
    for attempt in range(1, 4):                              # ≤3 tries
        try:
            print(f"[{label}] → {url}  (try {attempt})")
            page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_selector(item_sel, timeout=90_000)
            _scroll_to_bottom(page)

            rows = []
            for card in page.query_selector_all(item_sel):
                a = card.query_selector("h3 a, h2 a, a")
                if not a:
                    continue
                title = a.inner_text().strip()
                href = (a.get_attribute("href") or "").strip()
                if href.startswith("/"):
                    href = f"https://www.rbnz.govt.nz{href}"
                d_node = card.query_selector(
                    "time, .published-date, .result-date, span.date")
                date_txt = d_node.inner_text() if d_node else ""
                rows.append((title, href, _clean_date(date_txt)))
            return rows

        except TimeoutError as e:
            print(f"⚠️  Timeout on {label}: {e}")
            wait = 2 ** attempt
            print(f"   …retrying in {wait}s")
            time.sleep(wait)
    print(f"⚠️  Gave up on {label}")
    return []


# ─────────────────────── scrape orchestration ────────────────────────────────
def scrape() -> List[Tuple[str, str, str]]:
    targets = [
        ("news",
         "https://www.rbnz.govt.nz/news-and-events/news"
         "?sort=@computedz95xpublisheddate%20descending"),
        ("publications",
         "https://www.rbnz.govt.nz/research-and-publications/publications/publications-library"
         "?sort=@computedsortdate%20descending&"
         "f:@hierarchicalz95xsz120xacontenttypetagnames=[Publication]"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
                                    args=["--disable-blink-features=AutomationControlled"])
        page = browser.new_page(user_agent=UA)

        # Abort heavy / tracking assets for speed
        page.route(
            "**/*",
            lambda route, req: route.abort()
            if req.resource_type in {"image", "font", "stylesheet", "media"}
            else route.continue_())

        merged, seen = [], set()
        for label, url in targets:
            for t, u, d in _extract(page, label, url):
                if (t, u) not in seen:
                    merged.append((t, u, d))
                    seen.add((t, u))

        browser.close()
    return merged


# ────────────────────────── main ──────────────────────────────────────────────
def main():
    rows = scrape()
    now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(f"rbnz_articles_{now}.csv")

    with out_file.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["title", "url", "published_date"])
        w.writerows(rows)

    print(f"\n--- {len(rows)} rows collected ---")
    for t, u, d in rows[:10]:
        print(f"{d or 'N/A':<10}  {t}\n   {u}")
    print(f"\n✅  CSV saved  →  {out_file.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted by user")
