import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fma.govt.nz"
LIST_URL = f"{BASE_URL}/news/all-releases/media-releases/"

# Simple browser-like session so the site is happy
session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
)

# Date like "19 November 2025"
DATE_RE = re.compile(r"\b(\d{1,2} [A-Za-z]+ 20\d{2})\b")


def parse_list_page(url: str):
    """Parse one media-releases list page and return (items, next_url)."""
    resp = session.get(url, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    # Each result is headed by an <h3> with a link to the article
    for h3 in soup.find_all("h3"):
        a = h3.find("a", href=True)
        if not a:
            continue

        href = urljoin(BASE_URL, a["href"])
        # Only keep actual media-release articles
        if "/news/all-releases/media-releases/" not in href:
            continue

        title = a.get_text(strip=True)
        if not title:
            continue

        # Look in following siblings for a date line
        date = None
        for sib in h3.next_siblings:
            name = getattr(sib, "name", None)
            if name is None:
                text = str(sib).strip()
            else:
                text = sib.get_text(" ", strip=True)

            if not text:
                continue

            m = DATE_RE.search(text)
            if m:
                date = m.group(1)
                break

            # If we hit another heading, we've gone into the next item
            if name == "h3":
                break

        items.append(
            {
                "title": title,
                "url": href,
                "date": date,
            }
        )

    # Find the "Next >" pagination link, if present
    next_link = soup.find("a", string=lambda s: s and "Next" in s)
    next_url = urljoin(BASE_URL, next_link["href"]) if next_link else None

    return items, next_url


def scrape_fma_media_releases(max_pages: int | None = None):
    """
    Scrape media releases starting from LIST_URL.
    Set max_pages=None to go through all pages, or to an int to limit.
    """
    url = LIST_URL
    page = 0
    all_items = []

    while url:
        page += 1
        print(f"Fetching page {page}: {url}")
        items, next_url = parse_list_page(url)
        all_items.extend(items)

        if max_pages is not None and page >= max_pages:
            break

        if not next_url or next_url == url:
            break

        url = next_url

    return all_items


if __name__ == "__main__":
    # Change max_pages to None if you want to crawl all pages
    releases = scrape_fma_media_releases(max_pages=1)

    for r in releases:
        print(f"{r['date']}\t{r['title']}\t{r['url']}")
