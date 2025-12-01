import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import csv
import json
import time
from datetime import datetime


def normalize_date_to_iso(date_str: str) -> str:
    """
    Convert a human-readable date like '28 November 2025'
    (or similar) to 'YYYY-MM-DD'. Returns '' on failure.
    """
    if not date_str:
        return ""

    date_str = " ".join(date_str.split())  # normalize spaces

    # Try a few common formats
    formats = [
        "%d %B %Y",   # 28 November 2025
        "%d %b %Y",   # 28 Nov 2025
        "%A %d %B %Y" # Friday 28 November 2025
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # If parsing fails, return empty string
    return ""


def fetch_media_releases():
    base_url = "https://www.fma.govt.nz"
    url = "https://www.fma.govt.nz/news/all-releases/media-releases/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.88 Safari/537.36"
        )
    }

    releases = []
    visited_urls = set()

    while True:
        if url in visited_urls:
            print(f"[STOP] Loop detected, stopping at {url}")
            break

        visited_urls.add(url)
        print(f"Fetching: {url}")

        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract each article entry
        for item in soup.find_all("li", class_="search-results-semantic__result-item"):
            h3 = item.find("h3")
            a = h3.find("a") if h3 else None
            title = a.get_text(strip=True) if a else None
            article_url = urljoin(base_url, a["href"]) if a else None

            date_tag = item.find("span", class_="search-results-semantic__date")
            date_text = date_tag.get_text(strip=True) if date_tag else None

            if title and article_url and date_text:
                releases.append({
                    "title": title,
                    "url": article_url,
                    "date": date_text
                })

        # Detect next page
        next_link = soup.find("a", class_="next page-link")
        if not next_link:
            break

        next_href = next_link.get("href")
        if not next_href:
            break

        # Build next URL
        url = urljoin(base_url, next_href)

        # Prevent hammering server
        time.sleep(0.5)

    return releases


def save_results(releases):
    # Append to a shared results file in (yyyy-mm-dd, title, url) format
    results_csv = "results.csv"
    with open(results_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for r in releases:
            iso_date = normalize_date_to_iso(r["date"])
            writer.writerow([iso_date, r["title"], r["url"]])

    # (Optional) still save JSON if you find it useful
    json_filename = "fma_media_releases.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(releases, f, indent=2, ensure_ascii=False)

    print(f"\nAppended {len(releases)} articles to {results_csv}")
    print(f"Also saved raw data to {json_filename}")


if __name__ == "__main__":
    releases = fetch_media_releases()
    print(f"\nTotal releases scraped: {len(releases)}")

    # Print first few with normalized dates
    for r in releases[:10]:
        iso_date = normalize_date_to_iso(r["date"])
        print(f"{iso_date} | {r['title']} | {r['url']}")

    save_results(releases)
