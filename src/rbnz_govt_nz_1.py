"""
rbnz_scraper
================

This module provides a small utility for scraping lists of news releases and
publications from the Reserve Bank of New Zealand's website.  The public
pages on rbnz.govt.nz are rendered by the Coveo search platform.  At
run‑time the website fetches results from a Coveo search service using a
short‑lived JWT and an advanced query expression.  The token and other
configuration values are exposed in the page source as part of the
``window.RBNZ_COVEO_CONFIG`` JavaScript object, and the advanced query
expression for a given search tab lives in the page's ``dataExpression``.

This script automates the following steps:

1.  Download the source of a RBNZ search listing page (e.g. the News page
    or the Publications library) and extract the Coveo search token and
    REST endpoint.
2.  Locate and parse the ``dataExpression`` associated with the search
    interface to obtain the advanced query used by the website.  On the
    news page this filters results to items where
    ``@z95xtemplatename="News Page"``.  On the publications page the
    expression enumerates a number of internal template and tag IDs; the
    parser simply grabs the first quoted expression in the array and uses
    it as the advanced query.  If no ``dataExpression`` is found, you can
    optionally provide your own advanced query.
3.  Perform a POST request against the Coveo search API using the
    extracted configuration.  The request uses the advanced query
    expression, sorts results by the desired date field, and requests a
    set of fields to include in the response.  The script returns a list
    of tuples containing the title, URL and date for each result.

Example usage::

    from rbnz_scraper import fetch_rbnz_items

    # Fetch the most recent 50 news articles
    news_items = fetch_rbnz_items(
        page_url="https://www.rbnz.govt.nz/news-and-events/news",
        sort_field="@computedz95xpublisheddate",
        max_results=50
    )

    for title, url, date in news_items:
        print(f"{date} – {title} ({url})")

The function will automatically derive the advanced query from the page
source.  If desired you can override it by passing the ``advanced_query``
keyword argument.

Note: The JWT tokens embedded in the page source are time‑limited and
intended for client‑side use only.  They may expire after several
minutes.  If you receive an HTTP 401 response from the search endpoint,
call ``fetch_rbnz_items`` again so that it can refresh the token.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import requests


@dataclass
class CoveoConfig:
    """Configuration extracted from an RBNZ page for executing search queries.

    Attributes
    ----------
    token: str
        A short‑lived JWT used to authorise requests against the Coveo search API.
    rest_endpoint: str
        The base URL for the Coveo search endpoint (e.g. ``https://…/rest/search``).
    advanced_query: str
        An advanced query (Coveo's ``aq`` parameter) used to filter results.  This
        may be inferred from the page's ``dataExpression`` or provided by the user.
    """

    token: str
    rest_endpoint: str
    advanced_query: str


def _extract_token_and_endpoint(html: str) -> Tuple[str, str]:
    """Extract the Coveo token and REST endpoint from the supplied HTML.

    The page source exposes a JavaScript object ``window.RBNZ_COVEO_CONFIG``
    which holds the search configuration.  The token and endpoint are
    specified as e.g. ``token: "…"`` and ``restEndpoint: "…"``.  This
    helper locates these properties using regular expressions.

    Parameters
    ----------
    html: str
        The raw HTML source of the RBNZ page (view‑source).

    Returns
    -------
    Tuple[str, str]
        A tuple of ``(token, rest_endpoint)``.

    Raises
    ------
    ValueError
        If either property cannot be found.
    """
    token_match = re.search(r"token:\s*\"([^\"]+)\"", html)
    endpoint_match = re.search(r"restEndpoint:\s*\"([^\"]+)\"", html)
    if not token_match:
        raise ValueError("Unable to locate Coveo token in page source")
    if not endpoint_match:
        raise ValueError("Unable to locate Coveo REST endpoint in page source")
    token = token_match.group(1)
    endpoint = endpoint_match.group(1)
    return token, endpoint


def _extract_advanced_query(html: str) -> Optional[str]:
    """Extract the advanced query from the page's ``dataExpression``.

    The search interface on the site defines a ``dataExpression`` array for
    each search tab.  The first non‑empty string in this array contains an
    advanced query expression (AQ) encoded using single quotes.  This
    function attempts to extract the first quoted string from the
    ``dataExpression`` definition.

    Parameters
    ----------
    html: str
        The raw HTML source of the page (view‑source).

    Returns
    -------
    Optional[str]
        The advanced query string if found, otherwise ``None``.
    """
    # Locate the dataExpression array.  It may contain a leading comma
    # followed by a quoted expression.
    de_match = re.search(r'"dataExpression"\s*:\s*\[([^\]]+)\]', html, re.S)
    if not de_match:
        return None
    array_content = de_match.group(1)
    # Find the first single‑quoted string in the array.  The expression may
    # span multiple lines, so use DOTALL.
    expr_match = re.search(r"'([^']+)'", array_content, re.S)
    if expr_match:
        return expr_match.group(1).strip()
    return None


def _fetch_html_source(url: str) -> str:
    """Download the HTML source for a page.

    The RBNZ pages embed their search configuration directly in the
    HTML; there is no need to use the ``view-source:`` scheme.  This helper
    simply issues a GET request against the provided URL using a modern
    User‑Agent.  If your environment requires viewing the page source via
    the ``view-source:`` protocol you can substitute ``url`` with
    ``view-source:`` + ``url`` before calling this function; however
    ``requests`` does not recognise that scheme by default.

    Parameters
    ----------
    url: str
        The canonical page URL.  Must include the scheme (``http`` or
        ``https``).

    Returns
    -------
    str
        The raw HTML of the page.

    Raises
    ------
    HTTPError
        If the request fails.
    """
    if not re.match(r'^https?://', url):
        raise ValueError(f"Invalid URL: {url}")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text


def _execute_coveo_query(
    endpoint: str,
    token: str,
    aq: str,
    sort_field: str,
    max_results: int,
    fields: Iterable[str],
) -> List[dict]:
    """Execute a search query against the Coveo REST API.

    Parameters
    ----------
    endpoint: str
        Base URL of the Coveo search endpoint (should end in ``/rest/search``).
    token: str
        JWT used for authorisation.
    aq: str
        Advanced query string to filter results.
    sort_field: str
        Field by which to sort (e.g. ``@computedz95xpublisheddate``).  The
        API sorts descending by default when ``sortCriteria`` is set to
        ``fielddescending``.
    max_results: int
        Maximum number of results to return.
    fields: Iterable[str]
        Additional fields to include in the response.

    Returns
    -------
    List[dict]
        List of result objects returned by the API.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "q": "",  # empty keyword search – rely on the advanced query
        "aq": aq,
        "numberOfResults": max_results,
        "sortCriteria": "fielddescending",
        "sortField": sort_field,
        "fieldsToInclude": list(fields),
    }
    response = requests.post(endpoint, headers=headers, json=payload)
    # If the token has expired the API returns 401.  Propagate a clear
    # message to help the caller refresh the page source (and thus the token).
    if response.status_code == 401:
        raise RuntimeError(
            "Unauthorised: the Coveo token may have expired. "
            "Re‑fetch the page source to obtain a fresh token."
        )
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


def fetch_rbnz_items(
    page_url: str,
    sort_field: str,
    max_results: int = 100,
    advanced_query: Optional[str] = None,
) -> List[Tuple[str, str, str]]:
    """Scrape title, URL and date fields from an RBNZ search listing page.

    This convenience function orchestrates the extraction of configuration
    values and the execution of a search query.  It returns a list of
    ``(title, url, date)`` tuples.

    Parameters
    ----------
    page_url: str
        The URL of the RBNZ listing page (e.g. the news or publications
        library page).  Do not include the ``view-source:`` prefix.
    sort_field: str
        The Coveo field used for sorting and to extract the date from.
        For news pages use ``@computedz95xpublisheddate`` and for the
        publications library use ``@computedsortdate``.
    max_results: int, optional
        Maximum number of results to return (default 100).  Increase
        this number to retrieve more items.
    advanced_query: str, optional
        Override the advanced query extracted from the page's
        ``dataExpression``.  When ``None`` (the default) the function
        attempts to parse the advanced query from the page.  If no
        query is found this argument must be supplied.

    Returns
    -------
    List[Tuple[str, str, str]]
        A list of ``(title, url, date)`` tuples.  The date value is
        returned as a string exactly as provided by the API (ISO‐8601).

    Raises
    ------
    RuntimeError
        If the page configuration cannot be extracted or the API call
        returns an error.
    """
    html = _fetch_html_source(page_url)
    token, endpoint = _extract_token_and_endpoint(html)
    aq = advanced_query or _extract_advanced_query(html)
    if not aq:
        raise RuntimeError(
            "Unable to determine the advanced query from the page. "
            "Please provide the `advanced_query` parameter manually."
        )
    # Determine which raw field corresponds to the sort field by stripping
    # the leading '@'.  This allows us to look up the date inside the
    # returned result's 'raw' dictionary.
    raw_date_field = sort_field.lstrip('@')
    # Always include the title and date fields as well as clickUri.
    extra_fields = {"computedtitle", raw_date_field, "clickuri"}
    results = _execute_coveo_query(
        endpoint=endpoint,
        token=token,
        aq=aq,
        sort_field=sort_field,
        max_results=max_results,
        fields=extra_fields,
    )
    items: List[Tuple[str, str, str]] = []
    for result in results:
        # `clickUri` is the full URL to the result.  The title may be
        # contained in `raw.computedtitle` or, as a fallback, the top
        # level `title` property.
        raw = result.get("raw", {})
        title = raw.get("computedtitle") or result.get("title") or ""
        url = result.get("clickUri")
        date = raw.get(raw_date_field)
        items.append((title, url, date))
    return items


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for running the module as a script.

    When executed without arguments, the script fetches a sample of items
    from both the news page and the publications library and prints the
    results.  You may pass either ``news`` or ``publications`` as a
    positional argument to restrict the output to that section.  For
    example::

        python rbnz_scraper.py news
        python rbnz_scraper.py publications

    Parameters
    ----------
    argv: List[str], optional
        Command line arguments.  If ``None`` (default), ``sys.argv[1:]``
        will be used.

    Returns
    -------
    int
        Exit status code.  Zero indicates success.
    """
    if argv is None:
        argv = sys.argv[1:]
    # Determine which sections to fetch.  If no argument is supplied,
    # fetch both news and publications.
    sections: List[str]
    valid = {"news", "publications"}
    if not argv:
        sections = ["news", "publications"]
    else:
        unknown = [arg for arg in argv if arg not in valid]
        if unknown:
            print(
                f"Unknown section(s): {', '.join(unknown)}. "
                f"Valid options are 'news' or 'publications'.",
                file=sys.stderr,
            )
            return 1
        sections = argv
    # Configuration for each section
    config_map = {
        "news": {
            "page_url": "https://www.rbnz.govt.nz/news-and-events/news",
            "sort_field": "@computedz95xpublisheddate",
        },
        "publications": {
            "page_url": (
                "https://www.rbnz.govt.nz/research-and-publications/publications/"
                "publications-library"
            ),
            "sort_field": "@computedsortdate",
        },
    }
    exit_status = 0
    for section in sections:
        cfg = config_map[section]
        print(f"Fetching latest {section} from {cfg['page_url']}…")
        try:
            items = fetch_rbnz_items(
                cfg["page_url"], sort_field=cfg["sort_field"], max_results=10
            )
        except Exception as exc:
            print(f"Error fetching {section}: {exc}", file=sys.stderr)
            exit_status = 2
            continue
        for title, url, date in items:
            print(f"{date}\t{title}\t{url}")
        print()  # blank line between sections
    return exit_status


if __name__ == "__main__":
    # Run the main function and exit with its status code.  No exception
    # traceback will be printed for expected errors (e.g. network issues).
    raise SystemExit(main())
