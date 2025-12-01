#!/usr/bin/env python3
"""
Crawl RBA media releases, speeches and research pages and export
(article title, article url, article date, section) to a CSV file.

Sections:
  - https://www.rba.gov.au/media-releases/
  - https://www.rba.gov.au/speeches/
  - https://www.rba.gov.au/research/

Output:
  rba_articles_media_speeches_research.csv
"""

import csv
import re
import time
from collections import deque
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup


# --- HTTP helpers -----------------------------------------------------------

def make_session() -> requests.Session:
    """Create a requests.Session with a reasonable User-Agent."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    })
    return s


# --- Parsing helpers --------------------------------------------------------

DATE_META_NAME_PATTERN = re.compile(r"(DCTERMS\.issued|DC\.Date|dc\.date|dcterms\.issued)", re.I)
DATE_TEXT_PATTERN = re.compile(r"\b(\d{1,2} [A-Za-z]+ \d{4})\b")


def extract_title(soup: BeautifulSoup) -> str:
    """Best-effort extraction of article title."""
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return ""


def extract_date_strict(soup: BeautifulSoup) -> str | None:
    """
    'Strict' date extraction for deciding whether a page is an article.
    Only uses meta/time elements (not free text).
    """
    # Meta date (common on many gov sites)
    meta = soup.find("meta", attrs={"name": DATE_META_NAME_PATTERN})
    if meta and meta.get("content"):
        return meta["content"].strip()

    # <time> element, if present
    time_tag = soup.find("time")
    if time_tag and time_tag.get_text(strip=True):
        return time_tag.get_text(strip=True)

    # Sometimes date is in a dedicated element (class names vary)
    # Try a few common patterns but still keep it "strict"
    for cls in ["pub-date", "article-date", "release-date", "meta", "meta__date"]:
        el = soup.find(class_=cls)
        if el and el.get_text(strip=True):
            text = el.get_text(strip=True)
            m = DATE_TEXT_PATTERN.search(text)
            if m:
                return m.group(1)

    return None


def extract_date_fallback(soup: BeautifulSoup) -> str | None:
    """
    Fallback extraction: search for a date-like string anywhere in the text.
    Only used once we've already decided it's an article.
    """
    #  Limit text length to avoid being too slow
    text = soup.get_text(separator=" ", strip=True)
    text = text[:5000]  # safety
    m = DATE_TEXT_PATTERN.search(text)
    if m:
        return m.group(1)
    return None


def is_html_response(resp: requests.Response) -> bool:
    ctype = resp.headers.get("Content-Type", "")
    return "text/html" in ctype


def is_article_page(url_path: str, soup: BeautifulSoup) -> bool:
    """
    Heuristic: a page is an 'article' if we can find a 'strict' date.
    """
    date = extract_date_strict(soup)
    return date is not None


def is_same_section(base_path: str, candidate_path: str) -> bool:
    """
    Check if candidate_path is inside base_path.

    base_path is like '/media-releases/'.
    """
    if not base_path.endswith("/"):
        base_path = base_path + "/"
    return candidate_path.startswith(base_path)


NON_HTML_EXT_PATTERN = re.compile(
    r"\.(pdf|jpg|jpeg|png|gif|svg|doc|docx|xls|xlsx|zip|mp3|mp4|mov)$",
    re.I,
)


# --- Crawler for one section -----------------------------------------------

def crawl_section(session: requests.Session, base_url: str, section_name: str) -> list[dict]:
    """
    BFS-crawl all pages under base_url's path and collect article info.

    Returns:
        list of dicts: {section, title, url, date}
    """
    parsed_base = urlparse(base_url)
    base_path = parsed_base.path
    if not base_path.endswith("/"):
        base_path += "/"

    queue = deque([base_url])
    visited: set[str] = set()
    articles: list[dict] = []

    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[{section_name}] Error fetching {url}: {e}")
            continue

        if not is_html_response(resp):
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # If this looks like an article, extract info
        if is_article_page(urlparse(resp.url).path, soup):
            title = extract_title(soup)
            # Prefer strict date; if missing, try fallback
            date = extract_date_strict(soup) or extract_date_fallback(soup) or ""
            articles.append({
                "section": section_name,
                "title": title,
                "url": resp.url,
                "date": date,
            })

        # Enqueue more links inside the same section
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#"):
                continue

            full_url = urljoin(resp.url, href)
            parsed = urlparse(full_url)

            # stay on same host
            if parsed.netloc != parsed_base.netloc:
                continue

            # same section path only
            if not is_same_section(base_path, parsed.path):
                continue

            # skip non-html-looking endings
            if NON_HTML_EXT_PATTERN.search(parsed.path):
                continue

            if full_url not in visited:
                queue.append(full_url)

        # Be nice to the server
        time.sleep(0.3)

    return articles


# --- Main -------------------------------------------------------------------

def main():
    sections = {
        "media-releases": "https://www.rba.gov.au/media-releases/",
        "speeches": "https://www.rba.gov.au/speeches/",
        "research": "https://www.rba.gov.au/research/",
    }

    session = make_session()
    all_rows: list[dict] = []

    for name, url in sections.items():
        print(f"=== Crawling section: {name} ({url}) ===")
        section_rows = crawl_section(session, url, name)
        print(f"Collected {len(section_rows)} articles from {name}.")
        all_rows.extend(section_rows)

    output_file = "rba_articles_media_speeches_research.csv"
    fieldnames = ["section", "title", "url", "date"]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nSaved {len(all_rows)} articles to {output_file}")


if __name__ == "__main__":
    main()
