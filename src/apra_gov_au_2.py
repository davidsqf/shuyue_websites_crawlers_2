import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString

BASE_URL = "https://www.apra.gov.au"
LIST_URL = "https://www.apra.gov.au/news-and-publications/39"

# Matches dates like "28 November 2025"
DATE_RE = re.compile(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b")


def fetch_apra_articles():
    resp = requests.get(
        LIST_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            )
        },
        timeout=20,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    articles_by_url = {}

    # On this page, each news item is rendered as an <h4> heading
    # whose <a> child links to /news-and-publications/<slug>.
    for h4 in soup.find_all("h4"):
        a = h4.find("a", href=True)
        if not a:
            continue

        href = a["href"]
        # Keep only actual article links
        if "/news-and-publications/" not in href:
            continue

        full_url = urljoin(BASE_URL, href)
        title = " ".join(a.stripped_strings)

        # Avoid duplicates if any
        if full_url in articles_by_url:
            continue

        # --- Find the date text just before this heading ---
        # The page structure has the date immediately before the title,
        # so we walk backwards in the DOM and grab the first "dd Month yyyy".
        date_str = None
        node = h4
        steps = 0
        max_steps = 80  # safety limit

        while node is not None and steps < max_steps and date_str is None:
            node = node.previous_element
            steps += 1

            if isinstance(node, NavigableString):
                text = node.strip()
                if not text:
                    continue
                m = DATE_RE.search(text)
                if m:
                    date_str = m.group(0)
                    break

        articles_by_url[full_url] = {
            "title": title,
            "url": full_url,
            "date": date_str,
        }

    return list(articles_by_url.values())


if __name__ == "__main__":
    articles = fetch_apra_articles()
    for art in articles:
        print(f"{art['date']} | {art['title']} | {art['url']}")
