import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def fetch_media_releases() -> list[tuple[str, str, str]]:
    """
    Scrape all media releases from the FMA website.

    Returns:
        A list of tuples in the form (title, url, date).
    """
    base_url = "https://www.fma.govt.nz"
    url = "https://www.fma.govt.nz/news/all-releases/media-releases/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.88 Safari/537.36"
        )
    }

    releases: list[tuple[str, str, str]] = []

    while True:
        # Retrieve the page
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find all articles on this page
        for item in soup.find_all("li", class_="search-results-semantic__result-item"):
            heading = item.find("h3")
            link_tag = heading.find("a") if heading else None
            title = link_tag.get_text(strip=True) if link_tag else None
            article_url = urljoin(base_url, link_tag["href"]) if link_tag else None

            date_tag = item.find("span", class_="search-results-semantic__date")
            date = date_tag.get_text(strip=True) if date_tag else None

            if title and article_url and date:
                releases.append((title, article_url, date))

        # Check for a "Next" page link; if none, we're done
        next_link = soup.find("a", class_="next page-link")
        if not next_link or not next_link.get("href"):
            break
        url = urljoin(base_url, next_link["href"])

    return releases

if __name__ == "__main__":
    media_releases = fetch_media_releases()
    print(f"Scraped {len(media_releases)} releases:")
    for title, url, date in media_releases[:10]:
        print(f"{date} – {title} – {url}")
