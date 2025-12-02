from pathlib import Path

# Base directory for this repository (root that contains the src/ folder).
BASE_DIR = Path(__file__).resolve().parent.parent

# Folder to store scraper outputs so the web server can read them.
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Canonical output files for each scraper.
APRA_RESULTS = DATA_DIR / "apra_results.csv"
FMA_RESULTS = DATA_DIR / "fma_media_releases.csv"
RBNZ_RESULTS = DATA_DIR / "rbnz_latest_news.csv"
RBA_RESULTS = DATA_DIR / "rba_news_latest_100.csv"
