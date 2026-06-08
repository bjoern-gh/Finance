# Financial Analysis App

A stock analysis application that fetches live data from Yahoo Finance, calculates key metrics, and lets you manage multiple watchlists/portfolios. Built with Streamlit (UI), FastAPI (REST API), and yfinance.

---

## Features

- **Portfolio management** — create multiple named watchlists, add/remove stocks, data persists across restarts
- **Company search** — type a company name or ticker in the search box to find and add stocks; no need to know the exact symbol
- **File import** — upload a `.txt` or `.csv` with company names, plain tickers, or prefixed tickers; the app resolves them automatically
- **Metrics per stock** — Price, Currency, Price (EUR), SMA200, SMA50, RSI, P/E, Trend signal, Valuation, ATH/ATL, 52W High/Low %, Debt/Equity, Revenue Growth, Profit Margin, Beta, Sector, Dividend Yield, Market Cap
- **Trend signals** — STRONG BUY / BULLISH / OVERBOUGHT / HOLD / OVERSOLD / BEARISH, based on dual SMA + RSI + P/E
- **EUR conversion** — prices in non-EUR currencies (USD, GBp, CAD, etc.) are auto-converted using live FX rates
- **Color-coded table** — trend, valuation, RSI, and 52W distance are highlighted for quick scanning
- **Interactive charts** — candlestick price chart with SMA200, SMA50, and RSI subplot per stock
- **Export** — download results as CSV or Excel
- **REST API** — `/analyze` endpoint for programmatic access

### Supported exchanges

| Prefix | Exchange | Yahoo suffix |
|--------|----------|--------------|
| `FRA:` | Frankfurt | `.F` |
| `ETR:` | XETRA | `.DE` |
| `NASDAQ:` | NASDAQ | *(none)* |
| `NYSE:` | New York Stock Exchange | *(none)* |
| `LSE:` | London Stock Exchange | `.L` |
| `CVE:` | TSX Venture (Canada) | `.V` |
| `TSX:` | Toronto Stock Exchange | `.TO` |
| `EPA:` | Euronext Paris | `.PA` |
| `AMS:` | Euronext Amsterdam | `.AS` |
| `BIT:` | Borsa Italiana (Milan) | `.MI` |
| `BME:` | Bolsa de Madrid | `.MC` |
| `ASX:` | Australian Securities Exchange | `.AX` |
| `HKG:` | Hong Kong Stock Exchange | `.HK` |
| `TYO:` | Tokyo Stock Exchange | `.T` |
| `SWX:` | SIX Swiss Exchange | `.SW` |

Plain Yahoo Finance symbols (e.g. `AAPL`, `MSFT`) are also accepted without a prefix.

---

## Quick start with Docker (recommended)

Requires [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/).

### Step 1 — Clone the repo

```bash
git clone <repository_url>
cd Finance
```

### Step 2 — Set up user accounts

Copy the credentials template:

```bash
cp .env.example .env
```

Open `.env` in any text editor. You'll see:

```
AUTH_USERNAME=admin
AUTH_PASSWORD_HASH=your_sha256_hash_here
```

Replace `admin` with your chosen username, then generate a hash for your password:

```bash
python3 -c "import hashlib; print(hashlib.sha256(b'yourpassword').hexdigest())"
```

Paste the output as the value of `AUTH_PASSWORD_HASH`. Example finished `.env`:

```
AUTH_USERNAME=mladen
AUTH_PASSWORD_HASH=5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8
```

**Two accounts** (e.g. you and a friend) — use the plural keys with comma-separated values, keeping the order consistent:

```
AUTH_USERNAMES=mladen,friend
AUTH_PASSWORD_HASHES=<hash_for_mladen>,<hash_for_friend>
```

> `.env` is listed in `.gitignore` and `.dockerignore` — it will never be committed to git or baked into the Docker image.

### Step 3 — Build and start

```bash
docker-compose up --build -d
```

| Service | URL |
|---------|-----|
| Streamlit UI | http://localhost:8501 |
| FastAPI | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

Portfolio data is stored in a named Docker volume (`finance_portfolios`) and survives container restarts.

### Common commands

```bash
# Start (already built)
docker-compose up -d

# View live logs
docker-compose logs -f

# View logs for one service only
docker-compose logs -f streamlit
docker-compose logs -f api

# Stop containers (portfolio data is kept)
docker-compose down

# Rebuild after code changes
docker-compose up --build -d

# Stop and delete all portfolio data
docker-compose down -v
```

### Editing settings without rebuilding

`config.ini` is mounted read-only from the host into both containers, so you can change any setting and restart without a rebuild:

```bash
# Edit config.ini, then:
docker-compose restart
```

---

## Local development (without Docker)

### Prerequisites

- Python 3.11+

### Setup

```bash
git clone <repository_url>
cd Finance

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r dev-requirements.txt   # optional, for tests and linting
```

### Run the Streamlit app

```bash
streamlit run streamlit_app.py
```

Opens at http://localhost:8501.

### Run the API

```bash
uvicorn api:app --reload
```

Opens at http://localhost:8000. Interactive docs at http://localhost:8000/docs.

### Run the console analyser

```bash
python main.py
```

Reads tickers from `config.ini` → `raw_data`, prints results to the terminal.

---

## Using the app

### 1. Create a portfolio

Open the sidebar and click **＋ New**, give it a name, and click **Create**. You can have as many portfolios as you like and switch between them in the dropdown.

### 2. Add stocks

Go to the **Build Portfolio** tab.

**Search by name or ticker** — type anything in the search box (e.g. "Apple", "SAP", "ASML") and pick from the live results.

**Import from file** — upload a plain text or CSV file with one entry per line. Supported formats per line:

```
# Company names
Apple Inc
ASML Holding

# Plain Yahoo symbols
AAPL
MSFT

# Prefixed symbols
NASDAQ:NVDA
ETR:SAP
FRA:RWE
LSE:SHEL
```

The app will search unrecognised lines as company names and show you a confirmation table before adding anything.

### 3. Export and share a portfolio

At the bottom of the **Build Portfolio** tab there is an **Export / Import** section.

- **Export** — downloads the current portfolio as a `<name>.json` file. Send this file to a colleague or import it on another instance.
- **Import** — upload a previously exported `.json` file. You can rename it before saving. If a portfolio with that name already exists you will be warned before it is overwritten.

### 4. Run analysis

Switch to the **Analysis** tab and click **▶ Run Analysis**. Results are cached for 5 minutes — clicking the button again within that window returns instantly. Download the table as CSV or Excel using the buttons below the results.

**Trend signals explained:**

| Signal | Meaning |
|--------|---------|
| STRONG BUY | Price > SMA50 > SMA200, RSI 30–70, P/E below threshold |
| BULLISH | Price > SMA200, RSI 30–70, P/E below threshold |
| OVERBOUGHT | Price > SMA200 but RSI > 70 |
| HOLD | In uptrend but P/E too high, or neutral conditions |
| OVERSOLD | Price < SMA200 and RSI < 30 |
| BEARISH | Price < SMA200 |

**Valuation labels** are based on P/E ratio (configurable thresholds) refined by PEG ratio when earnings growth data is available.

### 4. Charts

Switch to the **Charts** tab, pick a stock from the dropdown and a time period. The chart shows a candlestick with SMA200 and SMA50 overlaid, plus an RSI subplot. If you have run the analysis, key metrics are shown above the chart.

### 5. API access

The `/analyze` endpoint accepts a comma-separated list of tickers:

```
GET http://localhost:8000/analyze?tickers=NASDAQ:AAPL,ETR:SAP,LSE:SHEL
```

If no `tickers` parameter is provided it uses the default list from `config.ini`. Full parameter documentation is available at `/docs`.

---

## Configuration

All settings live in `config.ini`. The file is mounted into Docker containers so changes take effect after a `docker-compose restart` without rebuilding.

```ini
[General]
# Default ticker list used by the API when no tickers are supplied
raw_data = NASDAQ:AAPL,ETR:SAP

sma_period = 200            # Long SMA period (days)
sma_short_period = 50       # Short SMA period (days)
rsi_period = 14             # RSI period (days)
kgv_max_threshold = 25      # Max P/E for BULLISH signal
history_period = 1y         # History window for SMA calculation

retries = 3                 # Yahoo Finance retry attempts per ticker
retry_delay_seconds = 5     # Delay between retries
max_workers = 10            # Parallel fetch threads

sort_by_column = KGV        # Column to sort results by (use English column names)
sort_ascending = True

ath_atl_threshold_percent = 5   # % proximity to ATH/ATL to trigger Near ATH/ATL label
pe_cheap_threshold = 15         # P/E below this → Cheap
pe_expensive_threshold = 30     # P/E above this → Expensive
peg_max_threshold = 1.0         # PEG below this → good PEG label

[Metrics]
include_dividend_yield = True
include_market_cap = True
```

---

## Project structure

```
Finance/
├── streamlit_app.py       # Streamlit UI — portfolios, search, analysis, charts
├── financial_analyzer.py  # Core logic — data fetch, metric calculation
├── portfolio_manager.py   # Portfolio CRUD — JSON files in portfolios/
├── api.py                 # FastAPI REST endpoint
├── main.py                # Console entry point
├── config.ini             # All configurable settings
├── requirements.txt       # Python dependencies
├── dev-requirements.txt   # Dev/test dependencies
├── Dockerfile             # Single image for both services
├── docker-compose.yml     # Orchestrates Streamlit + API + volume
├── .dockerignore
├── tests/
│   └── test_financial_analyzer.py
└── portfolios/            # Created at runtime, gitignored
    └── <name>.json        # One file per portfolio
```

---

## Running tests

```bash
# Activate venv first
pytest
```

## Code quality

```bash
black .           # Format
ruff check .      # Lint
ruff check . --fix  # Auto-fix lint issues
```
