#!/usr/bin/env python3
"""
Fetch (title, url, date) for
    • Media releases
    • Speeches
    • Research Discussion Papers (Research ⇒ RDPs)
from https://www.rba.gov.au.

Outputs: rba_articles.csv
"""
from __future__ import annotations
import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
HEADERS = {"User-Agent": (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36")}
ROOTS = {
    "media":  "https://www.rba.gov.au/media-releases/",
    "speech": "https://www.rba.gov.au/speeches/",
    # 2021-2025 page also links back to older decades, so start there
    "rdp":    "https://www.rba.gov.au/publications/rdp/2021-2030.html",
}
OUTFILE = Path("rba_articles.csv")
MAX_WORKERS = 12               # parallel article downloads
TIMEOUT = 30                   # seconds
DATE_RX_FULL   = re.compile(r"\b\d{1,2}\s+\w+\s+\d{4}\b")   # e.g. 26 November 2025
DATE_RX_YM     = re.compile(r"\b\w+\s+\d{4}\b")             # e.g. November 2025
YEAR_PAGE_RX   = re.compile(r"/(media-releases|speeches)/\d{4}/?$")

# --------------------------------------------------------------------------- #
# UTILS
# --------------------------------------------------------------------------- #
def get_soup(url: str) -> BeautifulSoup:
    """Download *url* and return BeautifulSoup(document)."""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def find_first_date(text: str) -> str | None:
    """Return first date-like substring or None."""
    m = DATE_RX_FULL.search(text)
    if m:
        return m.group(0).replace("\u00A0", " ").strip()  # normalise NBSP
    m2 = DATE_RX_YM.search(text)
    return m2.group(0).replace("\u00A0", " ").strip() if m2 else None

# --------------------------------------------------------------------------- #
# SCRAPERS
# --------------------------------------------------------------------------- #
def crawl_media_releases() -> List[Tuple[str, str, str]]:
    base = ROOTS["media"]
    soup = get_soup(base)
    # collect year sub-pages + main page
    year_hrefs = {urljoin(base, a["href"]) for a in soup.select("a[href]")
                  if YEAR_PAGE_RX.search(a["href"])}
    year_hrefs.add(base)  # latest listings often only on the root page
    article_links = set()
    for yurl in year_hrefs:
        ysoup = get_soup(yurl)
        # article pages look like …/YYYY/mr-YY-##.html
        for a in ysoup.select(f'a[href^="/media-releases/"]'):
            href = a["href"]
            if re.search(r"/\d{4}/mr-", href):          # filter nav junk
                article_links.add(urljoin(base, href))
    return _gather_article_meta(article_links)

def crawl_speeches() -> List[Tuple[str, str, str]]:
    base = ROOTS["speech"]
    soup = get_soup(base)
    year_hrefs = {urljoin(base, a["href"]) for a in soup.select("a[href]")
                  if YEAR_PAGE_RX.search(a["href"])}
    year_hrefs.add(base)
    article_links = set()
    for yurl in year_hrefs:
        ysoup = get_soup(yurl)
        for a in ysoup.select(f'a[href^="/speeches/"]'):
            href = a["href"]
            if re.search(r"/\d{4}/sp-.*\.html$", href):
                article_links.add(urljoin(base, href))
    return _gather_article_meta(article_links)

def crawl_rdps() -> List[Tuple[str, str, str]]:
    base = ROOTS["rdp"]
    soup = get_soup(base)
    article_links = {
        urljoin(base, a["href"])
        for a in soup.select('a[href^="/publications/rdp/"]')
        if re.search(r"/rdp/\d{4}/\d{4}-\d{2}\.html?$", a["href"])
    }
    return _gather_article_meta(article_links)

# --------------------------------------------------------------------------- #
# PARALLEL ARTICLE PARSER
# --------------------------------------------------------------------------- #
def _gather_article_meta(urls: Iterable[str]) -> List[Tuple[str, str, str]]:
    """
    For each article URL:
      • fetch page
      • extract title (h1 or first <title>)
      • extract first date occurrence
    Return list[ (title, url, date) ].
    """
    results: List[Tuple[str, str, str]] = []
    def _worker(u: str) -> Tuple[str, str, str]:
        psoup = get_soup(u)
        # title
        h1 = psoup.find("h1")
        title = h1.get_text(strip=True) if h1 else psoup.title.get_text(strip=True)
        # date – search whole page text once (cheap)
        date = find_first_date(psoup.get_text(" ", strip=True)) or "N/A"
        return title, u, date

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_worker, u): u for u in urls}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:
                print(f"[WARN] {futures[fut]} → {exc}")
    return results

# --------------------------------------------------------------------------- #
# TESTS (very light – keeps failing early mistakes out)
# --------------------------------------------------------------------------- #
def _tests() -> None:
    # date extraction utility
    assert find_first_date("Sydney – 26 November 2025") == "26 November 2025"
    assert find_first_date("November 2025") == "November 2025"
    # URL pattern sanity
    for root in ROOTS.values():
        assert urlparse(root).scheme.startswith("http")

# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #
def main() -> None:
    t0 = time.time()
    _tests()
    print("✔ basic self-tests passed – starting crawl ...")

    crawlers = [
        ("Media Releases", crawl_media_releases),
        ("Speeches",       crawl_speeches),
        ("Research RDPs",  crawl_rdps),
    ]
    all_rows: List[Tuple[str, str, str]] = []
    for label, fn in crawlers:
        print(f"  ↳ {label:15s} …", end="", flush=True)
        rows = fn()
        print(f"{len(rows):5d} articles")
        all_rows.extend(rows)

    # sort newest → oldest by date string (rough, but adequate)
    def _date_key(row):    # quiet fallback if day missing
        try:
            return time.strptime(row[2], "%d %B %Y")
        except ValueError:
            return time.strptime("01 " + row[2], "%d %B %Y")

    all_rows.sort(key=_date_key, reverse=True)

    # write CSV
    with OUTFILE.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["title", "url", "date"])
        w.writerows(all_rows)

    print(f"\n✓ Done – {len(all_rows)} total rows written to {OUTFILE.resolve()}")
    # echo to screen (first 10 rows)
    for r in all_rows[:10]:
        print(f"{r[2]:15s} | {r[0]}")

if __name__ == "__main__":
    main()
