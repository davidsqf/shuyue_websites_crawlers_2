import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import csv
import json
import time

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
            date = date_tag.get_text(strip=True) if date_tag else None

            if title and article_url and date:
                releases.append({
                    "title": title,
                    "url": article_url,
                    "date": date
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
    # Save CSV
    csv_filename = "fma_media_releases.csv"
    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "title", "url"])
        for r in releases:
            writer.writerow([r["date"], r["title"], r["url"]])

    # Save JSON
    json_filename = "fma_media_releases.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(releases, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(releases)} articles to:")
    print(f" - {csv_filename}")
    print(f" - {json_filename}")


if __name__ == "__main__":
    releases = fetch_media_releases()
    print(f"\nTotal releases scraped: {len(releases)}")

    # Print first few
    for r in releases[:10]:
        print(f"{r['date']} | {r['title']} | {r['url']}")

    save_results(releases)
