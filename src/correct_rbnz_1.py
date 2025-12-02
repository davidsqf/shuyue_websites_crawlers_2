#!/usr/bin/env python3
"""
Fetch the latest 30 RBNZ news items and save as CSV lines:

    YYYY-MM-DD,title,url

Source: official RBNZ news RSS feed:
  - https://www.rbnz.govt.nz/feeds/news
"""

import csv
import random
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Tuple
from xml.etree import ElementTree as ET

import requests

from logging_utils import setup_logger
from paths import RBNZ_RESULTS

FEED_URL = "https://www.rbnz.govt.nz/feeds/news"
OUTPUT_FILE = RBNZ_RESULTS
MAX_ITEMS = 30
logger = setup_logger("RBNZ")


# -------------------- "Human-like" HTTP session -------------------- #

def make_session() -> requests.Session:
    """Create a session with realistic browser-like headers."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-NZ,en;q=0.9",
        "Referer": "https://www.rbnz.govt.nz/news-and-events/news",
        "Connection": "keep-alive",
    })
    return s


def human_delay(base: float = 0.8, jitter: float = 0.7) -> None:
    """Sleep for a slightly random time to look less bot-like."""
    delay = base + random.random() * jitter
    time.sleep(delay)


# ------------------------- Date handling --------------------------- #

def parse_date_to_iso(date_str: str) -> str:
    """
    Convert various RSS/Atom date formats to YYYY-MM-DD.
    Returns '' on failure.
    """
    if not date_str:
        return ""

    date_str = date_str.strip()

    # 1) RFC-822 style (typical RSS <pubDate>)
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.date().isoformat()
    except Exception:
        pass

    # 2) ISO 8601 (typical Atom <updated>/<published>)
    try:
        cleaned = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.date().isoformat()
    except Exception:
        pass

    # 3) Fallback: "6 December 2012" or "6 Dec 2012"
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.date().isoformat()
        except Exception:
            continue

    return ""


# -------------------- Fetch & parse RSS/Atom ---------------------- #

def fetch_feed_xml(session: requests.Session,
                   url: str,
                   retries: int = 3,
                   timeout: int = 15) -> str:
    """
    Fetch the feed XML with a couple of retries and backoff.
    """
    for attempt in range(1, retries + 1):
        try:
            human_delay()  # small random delay before each attempt
            logger.info("Fetching feed (attempt %d/%d) from %s", attempt, retries, url)
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            logger.info("Feed fetched successfully")
            return resp.text
        except Exception as e:
            logger.warning("Attempt %d failed: %s", attempt, e)
            if attempt == retries:
                raise
            backoff = 2 ** (attempt - 1) + random.random()
            logger.info("Sleeping %.1fs before retry", backoff)
            time.sleep(backoff)

    raise RuntimeError("Unreachable: all retries exhausted but no exception raised.")


def extract_items(xml_text: str) -> List[Tuple[str, str, str]]:
    """
    Extract (iso_date, title, link) from RSS or Atom XML.
    """
    root = ET.fromstring(xml_text)
    items: List[Tuple[str, str, str]] = []

    # --- Try generic RSS 2.0: any <item> elements anywhere ---
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub_date_raw = (node.findtext("pubDate") or "").strip()
        iso_date = parse_date_to_iso(pub_date_raw)
        items.append((iso_date, title, link))

    # --- Fallback: Atom feed with <entry> elements ---
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns)
                     or "").strip()
            link_el = entry.find("atom:link", ns)
            link = ""
            if link_el is not None:
                link = link_el.attrib.get("href", "").strip()
            pub_raw = (
                entry.findtext("atom:published", default="", namespaces=ns)
                or entry.findtext("atom:updated", default="", namespaces=ns)
                or ""
            ).strip()
            iso_date = parse_date_to_iso(pub_raw)
            items.append((iso_date, title, link))

    # Sort by date descending if we have dates; undated items go last
    items.sort(key=lambda t: (t[0] or ""), reverse=True)
    return items


# --------------------------- CSV output --------------------------- #

def save_to_csv(rows: List[Tuple[str, str, str]], path: str) -> None:
    """
    Save rows as CSV *without* a header, lines like:
        2025-11-28,Some title,https://...
    The csv.writer will handle quoting if titles contain commas.
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for date_str, title, url in rows:
            writer.writerow([date_str, title, url])
    logger.info("Saved %d rows to %s", len(rows), path)


# ----------------------------- Main ------------------------------- #

def scrape_rbnz(save: bool = True) -> List[Tuple[str, str, str]]:
    session = make_session()
    try:
        xml_text = fetch_feed_xml(session, FEED_URL)
    except Exception as exc:
        logger.error("Failed to fetch feed: %s", exc)
        return []

    items = extract_items(xml_text)
    if not items:
        logger.warning("No items parsed from feed – nothing to save.")
        return []

    latest_30 = items[:MAX_ITEMS]
    if save:
        save_to_csv(latest_30, OUTPUT_FILE)

    for row in latest_30[:5]:
        logger.debug("%s | %s | %s", *row)

    logger.info("Prepared %d RBNZ articles", len(latest_30))
    return latest_30


def main() -> None:
    scrape_rbnz(save=True)


if __name__ == "__main__":
    main()
