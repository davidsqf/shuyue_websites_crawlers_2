from __future__ import annotations

import argparse
import csv
import html
import os
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

from correct_apra import scrape_apra
from correct_fma_govt_nz_2 import scrape_fma
from correct_rba_news_3 import scrape_rba
from correct_rbnz_1 import scrape_rbnz
from logging_utils import setup_logger
from paths import (
    APRA_RESULTS,
    DATA_DIR,
    FMA_RESULTS,
    RBA_RESULTS,
    RBNZ_RESULTS,
)

logger = setup_logger("WEB")

DEFAULT_REFRESH_SECONDS = 60 * 60  # 1 hour

SOURCES: Dict[str, Dict[str, Path | str]] = {
    "apra": {"title": "APRA News & Publications", "file": APRA_RESULTS},
    "fma": {"title": "FMA Media Releases", "file": FMA_RESULTS},
    "rbnz": {"title": "RBNZ News (latest 30)", "file": RBNZ_RESULTS},
    "rba": {"title": "RBA News (latest 100)", "file": RBA_RESULTS},
}

SCRAPE_FUNCS = {
    "apra": scrape_apra,
    "fma": scrape_fma,
    "rbnz": scrape_rbnz,
    "rba": scrape_rba,
}


def run_all_scrapers():
    """Run all source scrapers in parallel."""
    jobs = [(name.upper(), fn) for name, fn in SCRAPE_FUNCS.items()]
    threads = []

    def _runner(name, fn):
        try:
            logger.info("Starting %s scrape", name)
            fn(save=True)
            logger.info("Finished %s scrape", name)
        except Exception as exc:
            logger.error("%s scrape failed: %s", name, exc)

    for name, fn in jobs:
        t = threading.Thread(target=_runner, args=(name, fn), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()


def start_scrape_scheduler(interval_seconds: int) -> threading.Event:
    """
    Start a background thread that re-runs all scrapers every
    `interval_seconds`. Returns an event that can be set to stop the loop.
    """
    stop_event = threading.Event()
    min_interval = max(interval_seconds, 60)  # avoid noisy hammering

    def _worker():
        while not stop_event.wait(min_interval):
            run_all_scrapers()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    logger.info("Scheduled scrapers every %d seconds", min_interval)
    return stop_event


def read_rows(path: Path) -> List[Dict[str, str]]:
    """
    Read CSV rows as dictionaries with keys date/title/url.
    Missing files return an empty list.
    """
    if not path.exists():
        logger.warning("Results file not found: %s", path)
        return []

    rows: List[Dict[str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            date, title, url, *_ = row
            rows.append({"date": date, "title": title, "url": url})
    return rows


def format_timestamp(path: Path) -> str:
    if not path.exists():
        return "not found"
    ts = datetime.fromtimestamp(path.stat().st_mtime)
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def render_table(name: str, title: str, entries: List[Dict[str, str]], refresh_seconds: int) -> str:
    rows_html = "".join(
        f"<tr><td>{html.escape(entry['date'])}</td>"
        f"<td>{html.escape(entry['title'])}</td>"
        f"<td><a href='{html.escape(entry['url'])}' target='_blank' rel='noopener noreferrer'>link</a></td></tr>"
        for entry in entries
    )

    if not rows_html:
        rows_html = "<tr><td colspan='3' style='text-align:center'>No data available</td></tr>"

    auto_refresh_ms = max(refresh_seconds, 5) * 1000
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="refresh" content="{refresh_seconds}" />
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 24px;
      background: #f8fafc;
      color: #0f172a;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}
    a {{
      color: #0f6efd;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #e2e8f0;
    }}
    th {{
      text-align: left;
      background: #f1f5f9;
      font-weight: 600;
    }}
  </style>
  <script>
    setTimeout(() => window.location.reload(), {auto_refresh_ms});
  </script>
</head>
<body>
  <header>
    <div style="flex:1;">
      <h1 style="margin: 0;">{html.escape(title)}</h1>
      <p style="margin: 4px 0 0;">Auto-refresh every {refresh_seconds} seconds.</p>
    </div>
    <div style="display:flex; gap:8px; align-items:center;">
      <form method="post" action="/refresh/{name}" style="margin:0;">
        <button type="submit" style="padding:6px 12px; cursor:pointer;">Refresh now</button>
      </form>
      <button onclick="window.location.href='/'" style="padding:6px 12px; cursor:pointer;">Homepage</button>
    </div>
  </header>
  <table>
    <thead>
      <tr><th style="width: 120px;">Date</th><th>Title</th><th style="width: 70px;">Link</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""


def render_index(refresh_seconds: int) -> str:
    cards = []
    for slug, meta in SOURCES.items():
        path = Path(meta["file"])
        cards.append(
            f"<li><a href='/{slug}'><strong>{html.escape(meta['title'])}</strong></a>"
            f" — updated {format_timestamp(path)}</li>"
        )
    card_list = "\n".join(cards)
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="refresh" content="{refresh_seconds}" />
  <title>Scraper Results</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 24px;
      background: #f8fafc;
      color: #0f172a;
    }}
    h1 {{
      margin-bottom: 8px;
    }}
    ul {{
      padding-left: 18px;
    }}
  </style>
  <script>
    setTimeout(() => window.location.reload(), {refresh_seconds * 1000});
  </script>
</head>
<body>
  <h1>Scraper Results</h1>
  <p>Choose a source below. Pages auto-refresh every {refresh_seconds} seconds.</p>
  <ul>
    {card_list}
  </ul>
</body>
</html>
"""


class ResultsHandler(BaseHTTPRequestHandler):
    refresh_seconds: int = DEFAULT_REFRESH_SECONDS

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path.startswith("/refresh/"):
            slug = path.split("/refresh/", 1)[1]
            if slug in SCRAPE_FUNCS:
                self._trigger_refresh(slug)
                return
        self._respond(404, "<h1>404 Not Found</h1>")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            body = render_index(self.refresh_seconds)
            self._respond(200, body)
            return

        slug = path.lstrip("/")
        if slug in SOURCES:
            meta = SOURCES[slug]
            file_path = Path(meta["file"])
            entries = read_rows(file_path)
            body = render_table(slug, meta["title"], entries, self.refresh_seconds)
            self._respond(200, body)
            return

        self._respond(404, "<h1>404 Not Found</h1>")

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _respond(self, status: int, body: str):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _trigger_refresh(self, slug: str):
        fn = SCRAPE_FUNCS.get(slug)
        if not fn:
            self._respond(404, "<h1>Unknown source</h1>")
            return

        def _run():
            try:
                logger.info("Manual refresh requested for %s", slug)
                fn(save=True)
                logger.info("Manual refresh finished for %s", slug)
            except Exception as exc:
                logger.error("Manual refresh failed for %s: %s", slug, exc)

        threading.Thread(target=_run, daemon=True).start()
        body = f"""
<!DOCTYPE html>
<html><head>
  <meta http-equiv="refresh" content="1;url=/{slug}" />
  <title>Refreshing {slug}</title>
</head>
<body>
  <p>Refreshing {html.escape(slug)}... Redirecting back.</p>
</body></html>
"""
        self._respond(202, body)


def parse_args():
    parser = argparse.ArgumentParser(description="Serve scraper results over HTTP.")
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host to bind (default: 0.0.0.0 for LAN access)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Port to bind (default: 8000)",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=int,
        default=int(os.environ.get("REFRESH_SECONDS", DEFAULT_REFRESH_SECONDS)),
        help="Auto-refresh interval in seconds (default: 3600)",
    )
    parser.add_argument(
        "--scrape-interval",
        type=int,
        default=int(os.environ.get("SCRAPE_INTERVAL", DEFAULT_REFRESH_SECONDS)),
        help="How often to rerun scrapers in seconds (default: matches refresh interval)",
    )
    return parser.parse_args()


def guess_lan_ip() -> str | None:
    """
    Best-effort LAN IP discovery.
    Tries a UDP connect trick first, then falls back to hostname lookup.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return None


def main():
    args = parse_args()
    ResultsHandler.refresh_seconds = max(args.refresh_seconds, 5)
    scrape_interval = max(args.scrape_interval, 60)

    # Run scrapers once up-front so pages have data immediately (best effort).
    try:
        run_all_scrapers()
    except Exception as exc:  # pragma: no cover
        logger.error("Initial scraping failed; continuing to serve existing data: %s", exc)

    stop_event = start_scrape_scheduler(scrape_interval)

    server = ThreadingHTTPServer((args.host, args.port), ResultsHandler)
    local_url = f"http://localhost:{args.port}/"
    lan_ip = guess_lan_ip()
    lan_url = f"http://{lan_ip}:{args.port}/" if lan_ip else "LAN IP unavailable"

    logger.info(
        "Serving scraper results from %s (page refresh every %d s, scrape every %d s)",
        DATA_DIR,
        ResultsHandler.refresh_seconds,
        scrape_interval,
    )
    logger.info("Local access:   %s", local_url)
    if lan_ip:
        logger.info("LAN access:     %s", lan_url)
    else:
        logger.warning("LAN access:     unavailable (could not detect LAN IP)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server")
    finally:
        stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
