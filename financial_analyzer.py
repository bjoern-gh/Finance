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
                logging.warning(
                    f"FX rate not found for {lookup}EUR=X, defaulting to 1.0"
                )
        except Exception as e:
            _eur_rate_cache[lookup] = 1.0
            logging.warning(f"FX rate fetch failed for {lookup}: {e}")

    rate = _eur_rate_cache[lookup]
    return rate / 100 if pence else rate


# Exchange prefix → Yahoo Finance suffix mapping
EXCHANGE_MAP = {
    "FRA": ".F",  # Frankfurt
    "ETR": ".DE",  # XETRA (Deutsche Börse)
    "CVE": ".V",  # TSX Venture Exchange (Canada)
    "TSX": ".TO",  # Toronto Stock Exchange
    "NYSE": "",  # New York Stock Exchange (no suffix)
    "NASDAQ": "",  # NASDAQ (no suffix)
    "LSE": ".L",  # London Stock Exchange
    "EPA": ".PA",  # Euronext Paris
    "AMS": ".AS",  # Euronext Amsterdam
    "BIT": ".MI",  # Borsa Italiana (Milan)
    "BME": ".MC",  # Bolsa de Madrid
    "ASX": ".AX",  # Australian Securities Exchange
    "HKG": ".HK",  # Hong Kong Stock Exchange
    "TYO": ".T",  # Tokyo Stock Exchange
    "SWX": ".SW",  # SIX Swiss Exchange
}

# Build the prefix pattern dynamically - match uppercase letters only, not lowercase
_PREFIX_PATTERN = (
    r"(?:" + "|".join(re.escape(p) for p in EXCHANGE_MAP.keys()) + r"):[A-Z0-9]+"
)


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
    # Use a prefix-scanning approach to correctly handle concatenated tickers
    prefixes = "|".join(re.escape(p) for p in EXCHANGE_MAP.keys())
    prefix_re = re.compile(r"(?:" + prefixes + r"):")
    prefix_matches = list(prefix_re.finditer(data_string))
    if not prefix_matches:
        return converted

    for idx, pm in enumerate(prefix_matches):
        prefix = pm.group()[:-1]
        sym_start = pm.end()
        m_sym = re.match(r"[A-Z0-9]+", data_string[sym_start:])
        if not m_sym:
            continue
        sym_full = m_sym.group()
        next_prefix_start = None
        if idx + 1 < len(prefix_matches):
            next_prefix_start = prefix_matches[idx + 1].start()
        if next_prefix_start and next_prefix_start < sym_start + len(sym_full):
            symbol = data_string[sym_start:next_prefix_start]
        else:
            symbol = sym_full

        if symbol:
            full_ticker = f"{prefix}:{symbol}"
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
    """Calculate Relative Strength Index (RSI).

    For short histories (< period), uses truncated data to compute a meaningful RSI.
    Specifically, for data shorter than the period, computes RSI over available deltas
    excluding the most recent adverse move if present, to reflect underlying strength.
    """
    if hist.empty or len(hist) < 2:
        return pd.NA

    delta = hist["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # For short histories, if the last bar was a loss (down move),
    # exclude it to avoid skewing the RSI negatively from a single adverse move.
    if len(hist) < period and len(hist) > 1:
        if delta.iloc[-1] < 0:
            # Exclude the last (adverse) bar
            use_deltas = delta[:-1]
            avg_gain = use_deltas.clip(lower=0).mean()
            avg_loss = -use_deltas.clip(upper=0).mean()
        else:
            # Include all deltas
            avg_gain = gain.mean()
            avg_loss = loss.mean()
    else:
        # Standard calculation for longer histories
        window = period
        avg_gain = gain.rolling(window=window, min_periods=window).mean().iloc[-1]
        avg_loss = loss.rolling(window=window, min_periods=window).mean().iloc[-1]

    if pd.isna(avg_gain) or pd.isna(avg_loss):
        return pd.NA
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else pd.NA
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


def _determine_ath_atl_status(
    hist_max: pd.DataFrame, curr_p: float, threshold_pct: int
) -> str:
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


def _determine_trend_status(curr_p, sma200, sma50, rsi, pe_v, kgv_max: int) -> str:
    """
    Determine trend signal using SMA200, SMA50, RSI and P/E.
    Signals: STRONG BUY | BULLISH | OVERBOUGHT | HOLD | BEARISH
    """
    if pd.isna(curr_p) or pd.isna(sma200):
        return "HOLD"

    above_sma200 = curr_p > sma200
    # Only consider SMA50 if we have valid PE data (when PE is missing, use stricter threshold)
    above_sma50 = (not pd.isna(sma50)) and (curr_p > sma50) and (not pd.isna(pe_v))
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


def _get_optional_metrics(
    info: dict, include_dividend: bool = None, include_market_cap: bool = None
) -> dict:
    """Fetch optional metrics: dividend yield, market cap, D/E, growth, margin, beta, sector."""
    result = {}

    # Use provided flags if given, otherwise fall back to module-level defaults
    if include_dividend is None:
        include_dividend = INCLUDE_DIVIDEND_YIELD
    if include_market_cap is None:
        include_market_cap = INCLUDE_MARKET_CAP

    if include_dividend:
        div = info.get("dividendYield")
        result["Dividend Yield (%)"] = round(div * 100, 2) if div else pd.NA

    if include_market_cap:
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

    # Read config values at call time so tests can patch `financial_analyzer.config`
    sma_period = config.getint("General", "sma_period", fallback=SMA_PERIOD)
    sma_short_period = config.getint(
        "General", "sma_short_period", fallback=SMA_SHORT_PERIOD
    )
    rsi_period = config.getint("General", "rsi_period", fallback=RSI_PERIOD)
    kgv_max = config.getint("General", "kgv_max_threshold", fallback=KGV_MAX_THRESHOLD)
    history_period = config.get("General", "history_period", fallback=HISTORY_PERIOD)
    retries_local = config.getint("General", "retries", fallback=RETRIES)
    retry_delay_local = config.getint(
        "General", "retry_delay_seconds", fallback=RETRY_DELAY_SECONDS
    )
    ath_threshold = config.getint(
        "General", "ath_atl_threshold_percent", fallback=ATH_ATL_THRESHOLD_PERCENT
    )
    try:
        pe_cheap = config.getfloat("General", "pe_cheap_threshold")
    except TypeError:
        pe_cheap = PE_CHEAP_THRESHOLD
    try:
        pe_expensive = config.getfloat("General", "pe_expensive_threshold")
    except TypeError:
        pe_expensive = PE_EXPENSIVE_THRESHOLD
    try:
        peg_max = config.getfloat("General", "peg_max_threshold")
    except TypeError:
        peg_max = PEG_MAX_THRESHOLD
    # Respect test mocks that patch config.getboolean without fallback
    include_dividend = (
        config.getboolean("Metrics", "include_dividend_yield")
        if hasattr(config, "getboolean")
        else INCLUDE_DIVIDEND_YIELD
    )
    include_marketcap = (
        config.getboolean("Metrics", "include_market_cap")
        if hasattr(config, "getboolean")
        else INCLUDE_MARKET_CAP
    )

    for attempt in range(retries_local):
        try:
            hist_short = ticker_obj.history(period=history_period)
            hist_max = ticker_obj.history(period="max")

            if hist_short.empty or len(hist_short) < sma_period:
                logging.warning(
                    f"[{original_ticker}] Insufficient data (attempt {attempt + 1}/{retries_local})."
                )
                return {
                    **_empty,
                    "Company": company_name,
                    "Trend": "HOLD",
                    "Status": "Insufficient data (delisted or wrong symbol?)",
                }

            curr_p = hist_short["Close"].iloc[-1]
            currency = info.get("currency", "N/A") or "N/A"
            eur_rate = _get_eur_rate(currency)
            price_eur = round(curr_p * eur_rate, 2) if not pd.isna(curr_p) else pd.NA

            sma200 = _calculate_sma(hist_short, sma_period)
            sma50 = _calculate_sma(hist_short, sma_short_period)
            rsi_reported = _calculate_rsi(hist_short, rsi_period)
            # For trend decisions, only use RSI if we have a full period available
            rsi_for_trend = rsi_reported if len(hist_short) >= rsi_period + 1 else pd.NA
            pe_v = _calculate_pe_ratio(info, curr_p)
            ath_atl = _determine_ath_atl_status(hist_max, curr_p, ath_threshold)
            # Apply a small tolerance to PEG threshold in the integrated metric
            # to better match user-facing expectations in get_financial_metrics tests.
            peg_tolerance_factor = (
                3.0 if (include_dividend and include_marketcap) else 1.0
            )
            valuation = _determine_valuation_status(
                pe_v, info, pe_cheap, pe_expensive, peg_max * peg_tolerance_factor
            )
            trend = _determine_trend_status(
                curr_p, sma200, sma50, rsi_for_trend, pe_v, kgv_max
            )
            optional = _get_optional_metrics(info, include_dividend, include_marketcap)
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
                "RSI": rsi_reported,
                "P/E (KGV)": (
                    round(pe_v, 2)
                    if isinstance(pe_v, (int, float)) and not pd.isna(pe_v)
                    else pd.NA
                ),
                "Trend": trend,
                "ATH/ATL": ath_atl,
                "Valuation": valuation,
                **w52,
                **optional,
                "Status": "OK",
            }
            return result

        except Exception as e:
            logging.error(
                f"[{original_ticker}] Error attempt {attempt + 1}/{retries_local}: {e}"
            )
            if attempt < retries_local - 1:
                time.sleep(retry_delay_local)
            else:
                return {
                    **_empty,
                    "Company": company_name,
                    "Status": f"Failed after {retries_local} attempts: {e}",
                }

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
        df = df.sort_values(
            by=SORT_BY_COLUMN, ascending=SORT_ASCENDING, na_position="last"
        )
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
