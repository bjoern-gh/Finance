import yfinance as yf
import pandas as pd
import re
import configparser
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

# --- Logger setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# --- Load configuration ---
config = configparser.ConfigParser()
config.read("config.ini")

# General settings
SMA_PERIOD = config.getint("General", "sma_period")
SMA_SHORT_PERIOD = config.getint("General", "sma_short_period", fallback=50)
RSI_PERIOD = config.getint("General", "rsi_period", fallback=14)
KGV_MAX_THRESHOLD = config.getint("General", "kgv_max_threshold")
MAX_WORKERS = config.getint("General", "max_workers")
HISTORY_PERIOD = config.get("General", "history_period")
RETRIES = config.getint("General", "retries")
RETRY_DELAY_SECONDS = config.getint("General", "retry_delay_seconds")
SORT_BY_COLUMN = config.get("General", "sort_by_column")
SORT_ASCENDING = config.getboolean("General", "sort_ascending")
ATH_ATL_THRESHOLD_PERCENT = config.getint("General", "ath_atl_threshold_percent")

PE_CHEAP_THRESHOLD = config.getfloat("General", "pe_cheap_threshold")
PE_EXPENSIVE_THRESHOLD = config.getfloat("General", "pe_expensive_threshold")
PEG_MAX_THRESHOLD = config.getfloat("General", "peg_max_threshold")

INCLUDE_DIVIDEND_YIELD = config.getboolean("Metrics", "include_dividend_yield")
INCLUDE_MARKET_CAP = config.getboolean("Metrics", "include_market_cap")

# ── EUR FX rate cache (fetched once per process, reused across tickers) ──────
_eur_rate_cache: dict[str, float] = {}


def _get_eur_rate(currency: str) -> float:
    """
    Return the rate to multiply a price in `currency` to get EUR.
    Caches results so each FX pair is fetched at most once per run.
    Special case: 'GBp' (pence) = GBP / 100.
    """
    if not currency or currency == "EUR":
        return 1.0

    # Normalise pence → GBP first, remember the /100 factor
    pence = currency == "GBp"
    lookup = "GBP" if pence else currency

    if lookup not in _eur_rate_cache:
        try:
            ticker = yf.Ticker(f"{lookup}EUR=X")
            hist = ticker.history(period="1d")
            if not hist.empty:
                _eur_rate_cache[lookup] = float(hist["Close"].iloc[-1])
            else:
                _eur_rate_cache[lookup] = 1.0  # fallback: treat as 1:1
                logging.warning(f"FX rate not found for {lookup}EUR=X, defaulting to 1.0")
        except Exception as e:
            _eur_rate_cache[lookup] = 1.0
            logging.warning(f"FX rate fetch failed for {lookup}: {e}")

    rate = _eur_rate_cache[lookup]
    return rate / 100 if pence else rate

# Exchange prefix → Yahoo Finance suffix mapping
EXCHANGE_MAP = {
    "FRA": ".F",       # Frankfurt
    "ETR": ".DE",      # XETRA (Deutsche Börse)
    "CVE": ".V",       # TSX Venture Exchange (Canada)
    "TSX": ".TO",      # Toronto Stock Exchange
    "NYSE": "",        # New York Stock Exchange (no suffix)
    "NASDAQ": "",      # NASDAQ (no suffix)
    "LSE": ".L",       # London Stock Exchange
    "EPA": ".PA",      # Euronext Paris
    "AMS": ".AS",      # Euronext Amsterdam
    "BIT": ".MI",      # Borsa Italiana (Milan)
    "BME": ".MC",      # Bolsa de Madrid
    "ASX": ".AX",      # Australian Securities Exchange
    "HKG": ".HK",      # Hong Kong Stock Exchange
    "TYO": ".T",       # Tokyo Stock Exchange
    "SWX": ".SW",      # SIX Swiss Exchange
}

# Build the prefix pattern dynamically - match uppercase letters only, not lowercase
_PREFIX_PATTERN = r"(?:" + "|".join(re.escape(p) for p in EXCHANGE_MAP.keys()) + r"):[A-Z0-9]+"


def format_large_number(num):
    """Format large numbers into human-readable form (e.g. 1.23B, 45.6M)."""
    if not isinstance(num, (int, float)):
        return num
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return "%.2f%s" % (num, ["", "K", "M", "B", "T"][magnitude])


def parse_and_convert_tickers(data_string: str) -> list[tuple[str, str]]:
    """
    Extract ticker symbols from a raw string and convert to Yahoo Finance format.
    Uses regex to find all valid tickers (exchange:symbol format).
    Returns list of (original_ticker, yahoo_symbol) tuples.
    Supports: FRA, ETR, CVE, TSX, NYSE, NASDAQ, LSE, EPA, AMS, BIT, BME, ASX, HKG, TYO, SWX.
    """
    converted = []
    # Find all valid ticker patterns in the string using word boundaries
    matches = re.finditer(r'\b' + _PREFIX_PATTERN + r'\b', data_string)
    
    for match in matches:
        full_ticker = match.group()  # e.g., "FRA:R5A"
        parts = full_ticker.split(":", 1)
        if len(parts) == 2:
            prefix, symbol = parts
            suffix = EXCHANGE_MAP.get(prefix.upper(), "")
            yahoo_symbol = symbol + suffix
            converted.append((full_ticker, yahoo_symbol))
    
    return converted


# ── Metric calculation helpers ─────────────────────────────────���────────────

def _calculate_sma(hist: pd.DataFrame, period: int) -> float:
    """Calculate Simple Moving Average for the given period."""
    if hist.empty or len(hist) < period:
        return pd.NA
    return hist["Close"].rolling(window=period).mean().iloc[-1]


def _calculate_rsi(hist: pd.DataFrame, period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI)."""
    if hist.empty or len(hist) < period + 1:
        return pd.NA
    delta = hist["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]
    if pd.isna(avg_gain) or pd.isna(avg_loss):
        return pd.NA
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calculate_pe_ratio(info: dict, curr_p: float) -> float:
    """Calculate Price-to-Earnings ratio."""
    if pd.isna(curr_p):
        return pd.NA
    pe_v = info.get("trailingPE") or info.get("forwardPE")
    if pe_v is None or pe_v == "None":
        eps = info.get("trailingEps")
        pe_v = curr_p / eps if (eps and eps != 0) else pd.NA
    return pe_v


def _determine_ath_atl_status(hist_max: pd.DataFrame, curr_p: float, threshold_pct: int) -> str:
    """Determine if current price is near All-Time High or Low."""
    if hist_max.empty or pd.isna(curr_p):
        return "N/A"
    all_time_high = hist_max["High"].max()
    all_time_low = hist_max["Low"].min()
    if curr_p >= all_time_high * (1 - threshold_pct / 100):
        return "Near ATH"
    elif curr_p <= all_time_low * (1 + threshold_pct / 100):
        return "Near ATL"
    return "Normal"


def _determine_valuation_status(
    pe_v, info: dict, pe_cheap: float, pe_expensive: float, peg_max: float
) -> str:
    """Determine valuation label based on P/E and PEG ratios."""
    if not isinstance(pe_v, (int, float)) or pd.isna(pe_v):
        return "N/A"

    if pe_v <= pe_cheap:
        status = "Cheap"
    elif pe_v >= pe_expensive:
        status = "Expensive"
    else:
        status = "Fair"

    earnings_growth = info.get("earningsGrowth")
    if earnings_growth and earnings_growth > 0:
        peg_v = pe_v / (earnings_growth * 100)
        if peg_v <= peg_max:
            if status == "Cheap":
                status = "Very Cheap (PEG)"
            elif status == "Fair":
                status = "Fair (Good PEG)"
        else:
            if status == "Cheap":
                status = "Cheap (High PEG)"
            elif status == "Fair":
                status = "Fair (High PEG)"
            elif status == "Expensive":
                status = "Very Expensive (PEG)"
    return status


def _determine_trend_status(
    curr_p, sma200, sma50, rsi, pe_v, kgv_max: int
) -> str:
    """
    Determine trend signal using SMA200, SMA50, RSI and P/E.
    Signals: STRONG BUY | BULLISH | OVERBOUGHT | HOLD | BEARISH
    """
    if pd.isna(curr_p) or pd.isna(sma200):
        return "HOLD"

    above_sma200 = curr_p > sma200
    above_sma50 = (not pd.isna(sma50)) and (curr_p > sma50)
    rsi_ok = pd.isna(rsi) or (30 <= rsi <= 70)
    rsi_overbought = (not pd.isna(rsi)) and rsi > 70
    rsi_oversold = (not pd.isna(rsi)) and rsi < 30
    pe_ok = pd.isna(pe_v) or (isinstance(pe_v, (int, float)) and pe_v < kgv_max)

    if above_sma200 and above_sma50 and rsi_ok and pe_ok:
        return "STRONG BUY"
    elif above_sma200 and rsi_ok and pe_ok:
        return "BULLISH"
    elif above_sma200 and rsi_overbought:
        return "OVERBOUGHT"
    elif above_sma200 and not pe_ok:
        return "HOLD"
    elif not above_sma200 and rsi_oversold:
        return "OVERSOLD"
    elif not above_sma200:
        return "BEARISH"
    return "HOLD"


def _get_optional_metrics(info: dict) -> dict:
    """Fetch optional metrics: dividend yield, market cap, D/E, growth, margin, beta, sector."""
    result = {}

    if INCLUDE_DIVIDEND_YIELD:
        div = info.get("dividendYield")
        result["Dividend Yield (%)"] = round(div * 100, 2) if div else pd.NA

    if INCLUDE_MARKET_CAP:
        cap = info.get("marketCap")
        result["Market Cap"] = format_large_number(cap) if cap else pd.NA

    # Debt-to-Equity
    de = info.get("debtToEquity")
    result["D/E Ratio"] = round(de / 100, 2) if de else pd.NA

    # Revenue Growth (YoY %)
    rg = info.get("revenueGrowth")
    result["Revenue Growth (%)"] = round(rg * 100, 1) if rg is not None else pd.NA

    # Profit Margin (%)
    pm = info.get("profitMargins")
    result["Profit Margin (%)"] = round(pm * 100, 1) if pm is not None else pd.NA

    # Beta
    beta = info.get("beta")
    result["Beta"] = round(beta, 2) if beta else pd.NA

    # Sector
    result["Sector"] = info.get("sector", "N/A") or "N/A"

    return result


def _get_52w_metrics(info: dict, curr_p: float) -> dict:
    """Calculate 52-week high/low distance metrics."""
    high52 = info.get("fiftyTwoWeekHigh")
    low52 = info.get("fiftyTwoWeekLow")
    result = {}
    if high52 and not pd.isna(curr_p):
        result["52W High (%)"] = round((curr_p - high52) / high52 * 100, 1)
    else:
        result["52W High (%)"] = pd.NA
    if low52 and not pd.isna(curr_p):
        result["52W Low (%)"] = round((curr_p - low52) / low52 * 100, 1)
    else:
        result["52W Low (%)"] = pd.NA
    return result


# ── Main data fetcher ────────────────────────────────────────────────────────

def get_financial_metrics(ticker_tuple: tuple[str, str]) -> dict:
    """
    Fetch data from Yahoo Finance and compute all metrics for one ticker.
    Expects (original_ticker, yahoo_symbol) tuple.
    Implements retry logic.
    """
    original_ticker, yahoo_symbol = ticker_tuple

    _empty = {
        "Original Ticker": original_ticker,
        "Yahoo Symbol": yahoo_symbol,
        "Company": "N/A",
        "Price": pd.NA,
        "SMA200": pd.NA,
        "SMA50": pd.NA,
        "RSI": pd.NA,
        "P/E (KGV)": pd.NA,
        "Trend": "N/A",
        "ATH/ATL": "N/A",
        "Valuation": "N/A",
        "Currency": "N/A",
        "Price (EUR)": pd.NA,
        "52W High (%)": pd.NA,
        "52W Low (%)": pd.NA,
        "D/E Ratio": pd.NA,
        "Revenue Growth (%)": pd.NA,
        "Profit Margin (%)": pd.NA,
        "Beta": pd.NA,
        "Sector": "N/A",
    }
    if INCLUDE_DIVIDEND_YIELD:
        _empty["Dividend Yield (%)"] = pd.NA
    if INCLUDE_MARKET_CAP:
        _empty["Market Cap"] = pd.NA

    company_name = "N/A"
    info = {}

    try:
        ticker_obj = yf.Ticker(yahoo_symbol)
        info = ticker_obj.info
        company_name = info.get("longName") or info.get("shortName", "N/A")
    except Exception as e:
        logging.warning(f"[{original_ticker}] Info fetch failed: {e}")
        return {**_empty, "Company": company_name, "Status": f"Info fetch failed: {e}"}

    for attempt in range(RETRIES):
        try:
            hist_short = ticker_obj.history(period=HISTORY_PERIOD)
            hist_max = ticker_obj.history(period="max")

            if hist_short.empty or len(hist_short) < SMA_PERIOD:
                logging.warning(
                    f"[{original_ticker}] Insufficient data (attempt {attempt + 1}/{RETRIES})."
                )
                return {
                    **_empty,
                    "Company": company_name,
                    "Status": "Insufficient data (delisted or wrong symbol?)",
                }

            curr_p = hist_short["Close"].iloc[-1]
            currency = info.get("currency", "N/A") or "N/A"
            eur_rate = _get_eur_rate(currency)
            price_eur = round(curr_p * eur_rate, 2) if not pd.isna(curr_p) else pd.NA

            sma200 = _calculate_sma(hist_short, SMA_PERIOD)
            sma50 = _calculate_sma(hist_short, SMA_SHORT_PERIOD)
            rsi = _calculate_rsi(hist_short, RSI_PERIOD)
            pe_v = _calculate_pe_ratio(info, curr_p)
            ath_atl = _determine_ath_atl_status(hist_max, curr_p, ATH_ATL_THRESHOLD_PERCENT)
            valuation = _determine_valuation_status(
                pe_v, info, PE_CHEAP_THRESHOLD, PE_EXPENSIVE_THRESHOLD, PEG_MAX_THRESHOLD
            )
            trend = _determine_trend_status(curr_p, sma200, sma50, rsi, pe_v, KGV_MAX_THRESHOLD)
            optional = _get_optional_metrics(info)
            w52 = _get_52w_metrics(info, curr_p)

            result = {
                "Original Ticker": original_ticker,
                "Yahoo Symbol": yahoo_symbol,
                "Company": company_name,
                "Price": round(curr_p, 2) if not pd.isna(curr_p) else pd.NA,
                "Currency": currency,
                "Price (EUR)": price_eur if currency != "EUR" else pd.NA,
                "SMA200": round(sma200, 2) if not pd.isna(sma200) else pd.NA,
                "SMA50": round(sma50, 2) if not pd.isna(sma50) else pd.NA,
                "RSI": rsi,
                "P/E (KGV)": round(pe_v, 2) if isinstance(pe_v, (int, float)) and not pd.isna(pe_v) else pd.NA,
                "Trend": trend,
                "ATH/ATL": ath_atl,
                "Valuation": valuation,
                **w52,
                **optional,
                "Status": "OK",
            }
            return result

        except Exception as e:
            logging.error(f"[{original_ticker}] Error attempt {attempt + 1}/{RETRIES}: {e}")
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                return {**_empty, "Company": company_name, "Status": f"Failed after {RETRIES} attempts: {e}"}

    return {**_empty, "Company": company_name, "Status": "Unknown error"}


# ── Batch analyzer ─────────────────────────────────────────────────────────

def analyze_tickers(ticker_tuples_list: list[tuple[str, str]]) -> pd.DataFrame:
    """
    Analyze a list of (original_ticker, yahoo_symbol) tuples in parallel.
    Returns a sorted DataFrame with all metrics.
    """
    if not ticker_tuples_list:
        logging.warning("No tickers provided.")
        return pd.DataFrame()

    logging.info(f"Analyzing {len(ticker_tuples_list)} tickers (parallel).")
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for res in tqdm(
            executor.map(get_financial_metrics, ticker_tuples_list),
            total=len(ticker_tuples_list),
            desc="Processing tickers",
        ):
            results.append(res)

    df = pd.DataFrame(results)

    if SORT_BY_COLUMN in df.columns:
        df[SORT_BY_COLUMN] = pd.to_numeric(df[SORT_BY_COLUMN], errors="coerce")
        df = df.sort_values(by=SORT_BY_COLUMN, ascending=SORT_ASCENDING, na_position="last")
    else:
        logging.warning(f"Sort column '{SORT_BY_COLUMN}' not found.")

    return df


def get_price_history(yahoo_symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Fetch OHLCV history for a single ticker — used by the chart view.
    Returns DataFrame with Close, SMA200, SMA50 columns added.
    """
    try:
        ticker = yf.Ticker(yahoo_symbol)
        hist = ticker.history(period=period)
        if not hist.empty:
            hist["SMA200"] = hist["Close"].rolling(window=200).mean()
            hist["SMA50"] = hist["Close"].rolling(window=50).mean()
        return hist
    except Exception as e:
        logging.error(f"History fetch failed for {yahoo_symbol}: {e}")
        return pd.DataFrame()
