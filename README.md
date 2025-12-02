## Shuyue Website Crawlers – Quick Start (Windows and macOS)

This project scrapes four public sources (APRA, FMA, RBNZ, RBA) and serves the results on a small website. Each source page auto-refreshes, and you can manually refresh a single source from its page.

### 1) Prerequisites
- Python 3.10 or newer installed.
- Internet access (scrapers fetch public websites).
- A terminal:
  - Windows: PowerShell.
  - macOS: Terminal.

### 2) Get the code
If you already have the folder, open a terminal inside it. Otherwise:
- **Windows (PowerShell):**
  ```powershell
  git clone <this-repo-url> shuyue_websites_crawlers_2
  cd shuyue_websites_crawlers_2
  ```
- **macOS (Terminal):**
  ```bash
  git clone <this-repo-url> shuyue_websites_crawlers_2
  cd shuyue_websites_crawlers_2
  ```

### 3) Create and activate a virtual environment (no aliases assumed)
- **Windows (PowerShell):**
  ```powershell
  py -3 -m venv .venv
  .\.venv\Scripts\activate
  ```
- **macOS (Terminal):**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```
After activation your prompt should start with `(.venv)`.

### 4) Install dependencies
- **Windows (PowerShell):**
  ```powershell
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  ```
- **macOS (Terminal):**
  ```bash
  python3 -m pip install --upgrade pip
  python3 -m pip install -r requirements.txt
  ```
If you see SSL/proxy errors, add `--trusted-host pypi.org --trusted-host files.pythonhosted.org` to the install command.

### 5) Run the server
- **Windows (PowerShell):**
  ```powershell
  python src\web_server.py --host 0.0.0.0 --port 8000 --refresh-seconds 3600 --scrape-interval 3600
  ```
- **macOS (Terminal):**
  ```bash
  python3 src/web_server.py --host 0.0.0.0 --port 8000 --refresh-seconds 3600 --scrape-interval 3600
  ```
What the options mean:
- `--host 0.0.0.0` lets other machines on your LAN open the site. Use your LAN IP from step 6.
- `--port` is the port number (change if 8000 is taken).
- `--refresh-seconds` controls how often the webpage itself reloads.
- `--scrape-interval` controls how often the scrapers re-run in the background.
The two timers are independent.

### 6) Find your LAN IP
- **Windows:** run `ipconfig` in PowerShell. Look for “IPv4 Address” under your active network adapter (example: `192.168.1.23`).
- **macOS:** run `ipconfig getifaddr en0` (Wi‑Fi) or `ipconfig getifaddr en1` (Ethernet). Example output: `192.168.1.23`.
Other machines on the same network can open `http://<your-LAN-IP>:8000/` with that address.

### 7) Use the site
- Open `http://localhost:8000/` (or `http://<your-LAN-IP>:8000/` from another machine).
- Click a source (APRA/FMA/RBNZ/RBA) to see its table.
- On each source page:
  - **Refresh now**: manually triggers that crawler in the background.
  - **Homepage**: returns to the main list.
- Data files are stored in `data/` automatically.

### 8) Manual scraping (optional)
- **Windows (PowerShell):**
  ```powershell
  python src\correct_apra.py
  python src\correct_fma_govt_nz_2.py
  python src\correct_rbnz_1.py
  python src\correct_rba_news_3.py
  ```
- **macOS (Terminal):**
  ```bash
  python3 src/correct_apra.py
  python3 src/correct_fma_govt_nz_2.py
  python3 src/correct_rbnz_1.py
  python3 src/correct_rba_news_3.py
  ```
Normally the web server handles scraping for you.

### 9) Common issues and fixes
- **Port already in use**: pick another, e.g. `--port 8080`, then open `http://localhost:8080/`.
- **Nothing loads in browser**: check the server terminal for errors; ensure the URL/port is correct and your firewall allows the port.
- **Pip install fails**: confirm the virtual environment is active (`(.venv)`), upgrade pip, and add `--trusted-host` if behind a proxy.
- **Scrapers show errors**: temporary network or site changes can cause this; the server keeps running and serves any existing data. Try “Refresh now” later.
- **Deactivate the virtual environment**: run `deactivate`.

### 10) Stop the server
Press `Ctrl+C` in the terminal where the server is running.

### 11) Where things live
- Code: `src/`
- Generated data: `data/` (auto-created)
- Server entry point: `src/web_server.py`

You are ready—start the server, open the URL, and use the Refresh buttons when needed.***
