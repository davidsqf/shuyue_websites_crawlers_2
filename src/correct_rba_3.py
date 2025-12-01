#!/usr/bin/env python3
"""
Scrape RBA:
  • Media Releases    → rba_media_releases.csv
  • Speeches          → rba_speeches.csv
  • Research (RDPs)   → rba_research.csv
CSV columns: title, url, date
"""
from __future__ import annotations
import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, MINYEAR
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
SEEDS = {
    # human-readable entry points
    "media":  "https://www.rba.gov.au/media-releases/",
    "speech": "https://www.rba.gov.au/speeches/",
    "research_root": "https://www.rba.gov.au/research/",
}
# year-index pages for Research Discussion Papers
RDP_YEAR_PAGES = [                    # NB: hard-coded – avoids JS rendering issues
    "https://www.rba.gov.au/publications/rdp/2021-2030.html",
    "https://www.rba.gov.au/publications/rdp/2011-2020.html",
    "https://www.rba.gov.au/publications/rdp/2001-2010.html",
    "https://www.rba.gov.au/publications/rdp/1991-2000.html",
    "https://www.rba.gov.au/publications/rdp/1981-1990.html",
    "https://www.rba.gov.au/publications/rdp/1971-1980.html",
    "https://www.rba.gov.au/publications/rdp/1969-1970.html",
]
OUTFILES = {
    "media":   Path("rba_media_releases.csv"),
    "speech":  Path("rba_speeches.csv"),
    "research": Path("rba_research.csv"),
}
MAX_WORKERS = 12
TIMEOUT = 30
DATE_RX_FULL   = re.compile(r"\b\d{1,2}\s+\w+\s+\d{4}\b")   # 26 November 2025
DATE_RX_YM     = re.compile(r"\b\w+\s+\d{4}\b")             # November 2025
YEAR_PAGE_RX   = re.compile(r"/(media-releases|speeches)/\d{4}/?$")

# --------------------------------------------------------------------------- #
# UTILS
# --------------------------------------------------------------------------- #
def get_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def find_first_date(text: str) -> str | None:
    m = DATE_RX_FULL.search(text)
    if m:
        return m.group(0).replace("\u00A0", " ").strip()
    m2 = DATE_RX_YM.search(text)
    return m2.group(0).replace("\u00A0", " ").strip() if m2 else None

def date_key(date_str: str) -> datetime:
    for fmt in ("%d %B %Y", "%B %Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime(MINYEAR, 1, 1)

def gather_article_meta(urls: Iterable[str]) -> List[Tuple[str, str, str]]:
    """Fetch every article URL → (title, url, date)."""
    results: List[Tuple[str, str, str]] = []

    def _worker(u: str) -> Tuple[str, str, str]:
        psoup = get_soup(u)
        title = (psoup.find("h1") or psoup.title).get_text(strip=True)
        date  = find_first_date(psoup.get_text(" ", strip=True)) or "N/A"
        return title, u, date

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_worker, u): u for u in urls}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:
                print(f"[WARN] {futures[fut]} → {exc}")
    results.sort(key=lambda r: date_key(r[2]), reverse=True)
    return results

# --------------------------------------------------------------------------- #
# SCRAPERS
# --------------------------------------------------------------------------- #
def crawl_media_releases() -> List[Tuple[str, str, str]]:
    base = SEEDS["media"]
    soup = get_soup(base)
    year_hrefs = {urljoin(base, a["href"]) for a in soup.select("a[href]")
                  if YEAR_PAGE_RX.search(a["href"])}
    year_hrefs.add(base)
    article_links = set()
    for yurl in year_hrefs:
        ysoup = get_soup(yurl)
        for a in ysoup.select('a[href^="/media-releases/"]'):
            href = a["href"]
            if re.search(r"/\d{4}/mr-", href):
                article_links.add(urljoin(base, href))
    return gather_article_meta(article_links)

def crawl_speeches() -> List[Tuple[str, str, str]]:
    base = SEEDS["speech"]
    soup = get_soup(base)
    year_hrefs = {urljoin(base, a["href"]) for a in soup.select("a[href]")
                  if YEAR_PAGE_RX.search(a["href"])}
    year_hrefs.add(base)
    article_links = set()
    for yurl in year_hrefs:
        ysoup = get_soup(yurl)
        for a in ysoup.select('a[href^="/speeches/"]'):
            href = a["href"]
            if re.search(r"/\d{4}/sp-.*\.html?$", href):
                article_links.add(urljoin(base, href))
    return gather_article_meta(article_links)

def crawl_research() -> List[Tuple[str, str, str]]:
    """
    Research: scrape every Research Discussion Paper from the fixed
    year-index pages under /publications/rdp/.  (Avoids JS on /research/.)
    """
    article_links = set()
    for index_url in RDP_YEAR_PAGES:
        ysoup = get_soup(index_url)
        # RDP pages look like /publications/rdp/YYYY/yy-zz.html
        for a in ysoup.select('a[href^="/publications/rdp/"]'):
            href = a["href"]
            if re.search(r"/rdp/\d{4}/\d{4}-\d{2}\.html?$", href):
                article_links.add(urljoin(index_url, href))
    return gather_article_meta(article_links)

# --------------------------------------------------------------------------- #
# SELF-TESTS
# --------------------------------------------------------------------------- #
def _tests() -> None:
    assert find_first_date("Sydney 26 November 2025") == "26 November 2025"
    assert find_first_date("November 2025") == "November 2025"
    for url in SEEDS.values():
        assert urlparse(url).scheme.startswith("http")

# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #
def main() -> None:
    _tests()
    print("✔ basic self-tests passed – starting crawl ...")

    sections = [
        ("media",    "Media Releases", crawl_media_releases),
        ("speech",   "Speeches",       crawl_speeches),
        ("research", "Research (RDPs)", crawl_research),
    ]

    for key, label, fn in sections:
        print(f"  ↳ {label:17s} …", end="", flush=True)
        rows = fn()
        print(f"{len(rows):5d} articles")
        outfile = OUTFILES[key]
        with outfile.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([("title", "url", "date"), *rows])
        print(f"     → saved to {outfile.resolve()}")

    print("\n✓ All three files written successfully.")

if __name__ == "__main__":
    main()
