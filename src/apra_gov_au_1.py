import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.apra.gov.au"
LIST_URL = "https://www.apra.gov.au/news-and-publications/39"

DATE_RE = re.compile(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b")


def extract_articles(list_url: str):
    resp = requests.get(list_url, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try to restrict search to the main content area if present
    main = soup.find("main") or soup

    articles = []

    # On this page each item appears as a heading (h4) with a link,
    # and a date just above it (e.g. "28 November 2025").
    for heading in main.find_all(["h2", "h3", "h4"]):
        link = heading.find("a", href=True)
        if not link:
            continue

        href = link["href"]

        # Only keep actual news/publication items, not nav links
        if not href.startswith("/news-and-publications/"):
            continue

        title = link.get_text(strip=True)
        if title.lower() in {"news and publications", "show all"}:
            continue

        # Find the closest date text above this heading
        date_text = None

        # Search previous siblings within the same container first
        for parent in [heading] + list(heading.parents):
            prev = parent.previous_sibling
            while prev and not date_text:
                if isinstance(prev, str):
                    m = DATE_RE.search(prev)
                    if m:
                        date_text = m.group(0)
                        break
                else:
                    text = prev.get_text(" ", strip=True)
                    m = DATE_RE.search(text)
                    if m:
                        date_text = m.group(0)
                        break
                prev = prev.previous_sibling
            if date_text:
                break

        # Fallback: look anywhere just above in the document
        if not date_text:
            prev_text_node = heading.find_previous(string=DATE_RE)
            if prev_text_node:
                m = DATE_RE.search(prev_text_node)
                if m:
                    date_text = m.group(0)

        articles.append(
            {
                "date": date_text,
                "title": title,
                "url": urljoin(BASE_URL, href),
            }
        )

    return articles


if __name__ == "__main__":
    items = extract_articles(LIST_URL)
    for item in items:
        print(f"{item['date']} | {item['title']} | {item['url']}")
