"""
Scraper for the Reserve Bank of Australia (RBA) website.

This script collects titles, URLs and publication dates for three types of
content hosted on the RBA site:

* Media releases (https://www.rba.gov.au/media‑releases/)
* Speeches (https://www.rba.gov.au/speeches/)
* Research discussion papers (https://www.rba.gov.au/publications/rdp/)

For media releases and speeches the RBA provides index pages broken down
by year. Each index page contains a list of articles together with a
publication date. For research discussion papers the year index pages
contain links to the individual papers, but the dates are only
available on the article pages themselves. Consequently the scraper
must fetch each research paper page to retrieve its publication date
from the embedded metadata.

The script is written for Python 3 and relies on the requests and
BeautifulSoup libraries for HTTP requests and HTML parsing. It
includes helper functions to simplify date handling and to robustly
handle HTTP errors. If run as a program, the script will fetch all
available items from the three content types and print the number of
items collected for each category. It can easily be adapted to write
the results to disk or to further process the data.
"""

import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def get_soup(url: str, *, retries: int = 3, backoff: float = 1.0) -> BeautifulSoup:
    """Fetch a URL and return a BeautifulSoup object.

    Args:
        url: The URL to fetch.
        retries: Number of retries for transient failures.
        backoff: Backoff time in seconds between retries.

    Returns:
        BeautifulSoup instance parsed from the response content.

    Raises:
        requests.HTTPError: if the request fails after the given number of retries.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                # 404 or other non‑200 statuses are treated as errors.
                resp.raise_for_status()
            return BeautifulSoup(resp.content, "lxml")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff)
            else:
                # bubble up the exception after exhausting retries
                raise
    # Should never reach here, but mypy demands a return
    raise RuntimeError("Failed to fetch page") from last_exc


def parse_date_str(dt_str: str) -> str:
    """Normalise a date or datetime string to ISO date (YYYY‑MM‑DD).

    RBA pages sometimes provide dates in ISO datetime format
    (e.g. '2025-11-26T13:05+1100') and sometimes as plain dates
    ('2025-11-26'). This helper strips the time component and returns
    only the date portion. If the string cannot be parsed, the
    original string is returned unchanged.

    Args:
        dt_str: input date string

    Returns:
        The date portion (YYYY‑MM‑DD) if recognised, otherwise the
        original string.
    """
    # The date is before the 'T' if present
    if 'T' in dt_str:
        dt_str = dt_str.split('T')[0]
    # Validate ISO date format
    try:
        datetime.strptime(dt_str, "%Y-%m-%d")
        return dt_str
    except ValueError:
        return dt_str


def extract_media_releases() -> List[Dict[str, str]]:
    """Extract all media releases from the RBA site.

    Returns:
        A list of dicts with keys 'title', 'url', and 'date'.
    """
    base_url = "https://www.rba.gov.au"
    index_url = f"{base_url}/media-releases/"
    soup = get_soup(index_url)

    # Find year index links of the form /media-releases/XXXX/
    year_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.fullmatch(r"/media-releases/(\d{4})/", href)
        if m:
            year_links.add(href)

    results: List[Dict[str, str]] = []
    for rel in sorted(year_links):
        year_url = urljoin(base_url, rel)
        try:
            year_soup = get_soup(year_url)
        except requests.HTTPError:
            # Skip missing year pages
            continue
        # Each item is contained in a <li class="item ..."> element
        for li in year_soup.select("li.item"):
            # Title and link
            anchor = li.find("a", href=True)
            if not anchor:
                continue
            title = anchor.get_text(strip=True)
            url = urljoin(base_url, anchor["href"])
            # Date within <time datetime="YYYY-MM-DD">
            time_tag = li.find("time")
            date_iso = None
            if time_tag and time_tag.has_attr("datetime"):
                date_iso = parse_date_str(time_tag["datetime"])
            elif time_tag:
                date_iso = time_tag.get_text(strip=True)
            else:
                date_iso = ""
            results.append({"title": title, "url": url, "date": date_iso})
    return results


def extract_speeches() -> List[Dict[str, str]]:
    """Extract all speeches from the RBA site.

    Returns:
        A list of dicts with keys 'title', 'url', and 'date'.
    """
    base_url = "https://www.rba.gov.au"
    index_url = f"{base_url}/speeches/"
    soup = get_soup(index_url)

    # Find year index links of the form /speeches/XXXX/
    year_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.fullmatch(r"/speeches/(\d{4})/", href)
        if m:
            year_links.add(href)

    results: List[Dict[str, str]] = []
    for rel in sorted(year_links):
        year_url = urljoin(base_url, rel)
        try:
            year_soup = get_soup(year_url)
        except requests.HTTPError:
            continue
        # Each speech is inside a div with class 'rss-speech-item'
        for item in year_soup.select("div.item.rss-speech-item"):
            # Title and link: anchor with class 'rss-speech-html'
            anchor = item.find("a", class_="rss-speech-html")
            if not anchor:
                continue
            title = anchor.get_text(strip=True)
            url = urljoin(base_url, anchor["href"])
            # Date: <time> inside span date
            time_tag = item.find("time")
            date_iso = ""
            if time_tag and time_tag.has_attr("datetime"):
                date_iso = parse_date_str(time_tag["datetime"])
            elif time_tag:
                date_iso = time_tag.get_text(strip=True)
            results.append({"title": title, "url": url, "date": date_iso})
    return results


def extract_research() -> List[Dict[str, str]]:
    """Extract all research discussion papers from the RBA site.

    Returns:
        A list of dicts with keys 'title', 'url', and 'date'.
    """
    base_url = "https://www.rba.gov.au"
    results: List[Dict[str, str]] = []

    # RDP series starts from 1969; iterate through years up to current year
    current_year = datetime.now().year
    for year in range(1969, current_year + 1):
        year_url = f"{base_url}/publications/rdp/{year}/"
        try:
            year_soup = get_soup(year_url)
        except requests.HTTPError:
            # If the page does not exist (404), skip
            continue
        # Find article links with class rss-rdp-link
        for a in year_soup.select("a.rss-rdp-link"):
            href = a.get("href")
            if not href:
                continue
            title = a.get_text(strip=True)
            full_url = urljoin(base_url, href)
            # Fetch article page to extract date
            date_iso = ""
            try:
                article_soup = get_soup(full_url)
                # Prefer the dc.date meta tag which contains the ISO date
                meta_date = article_soup.find("meta", attrs={"name": "dc.date"})
                if meta_date and meta_date.has_attr("content"):
                    date_iso = parse_date_str(meta_date["content"])
                else:
                    # Fallback to dcterms.created if dc.date is missing
                    meta_created = article_soup.find("meta", attrs={"name": "dcterms.created"})
                    if meta_created and meta_created.has_attr("content"):
                        date_iso = parse_date_str(meta_created["content"])
            except Exception:
                # If article cannot be fetched, leave date empty
                pass
            results.append({"title": title, "url": full_url, "date": date_iso})
    return results


if __name__ == "__main__":
    # Fetch and print counts for testing purposes.
    media = extract_media_releases()
    print(f"Fetched {len(media)} media releases")
    speeches = extract_speeches()
    print(f"Fetched {len(speeches)} speeches")
    research = extract_research()
    print(f"Fetched {len(research)} research papers")