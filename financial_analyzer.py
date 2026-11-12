import concurrent.futures
import configparser
import logging
import re
import threading
import time
import warnings
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from tqdm import tqdm

# Suppress third-party deprecation warnings (e.g. yfinance internal inplace calls with pandas >= 3.0)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="^yfinance")
warnings.filterwarnings("ignore", category=FutureWarning, module="^yfinance")
warnings.filterwarnings("ignore", message=".*inplace.*")
try:
    from pandas.errors import Pandas4Warning

    warnings.filterwarnings("ignore", category=Pandas4Warning)
except ImportError:
    pass

# --- Logger setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

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
_eur_rate_lock = threading.Lock()


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

    with _eur_rate_lock:
        if lookup in _eur_rate_cache:
            rate = _eur_rate_cache[lookup]
            return rate / 100 if pence else rate

    # Fetch outside lock to avoid blocking other threads during network I/O
    try:
        ticker = yf.Ticker(f"{lookup}EUR=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
        else:
            rate = 1.0  # fallback: treat as 1:1
            logger.warning(f"FX rate not found for {lookup}EUR=X, defaulting to 1.0")
    except Exception as e:
        rate = 1.0
        logger.warning(f"FX rate fetch failed for {lookup}: {e}", exc_info=True)

    with _eur_rate_lock:
        _eur_rate_cache[lookup] = rate

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
_PREFIX_PATTERN = r"(?:" + "|".join(re.escape(p) for p in EXCHANGE_MAP) + r"):[A-Z0-9]+"


def format_large_number(num):
    """Format large numbers into human-readable form (e.g. 1.23B, 45.6M)."""
    if not isinstance(num, (int, float)):
        return num
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return "{:.2f}{}".format(num, ["", "K", "M", "B", "T"][magnitude])


def parse_and_convert_tickers(data_string: str) -> list[tuple[str, str]]:
    """
    Extract ticker symbols from a raw string and convert to Yahoo Finance format.
    Uses regex to find all valid tickers (exchange:symbol format).
    Returns list of (original_ticker, yahoo_symbol) tuples.
    Supports: FRA, ETR, CVE, TSX, NYSE, NASDAQ, LSE, EPA, AMS, BIT, BME, ASX, HKG, TYO, SWX.
    """
    converted = []
    # Use a prefix-scanning approach to correctly handle concatenated tickers
    prefixes = "|".join(re.escape(p) for p in EXCHANGE_MAP)
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


def _calculate_sma(hist: pd.DataFrame, period: int) -> float | Any:
    """Calculate Simple Moving Average for the given period."""
    if hist.empty or len(hist) < period:
        return pd.NA
    return hist["Close"].rolling(window=period).mean().iloc[-1]


def _calculate_rsi(hist: pd.DataFrame, period: int = 14) -> float | Any:
    """Calculate Relative Strength Index (RSI) using Wilder's Exponential Smoothing.

    For data with at least period + 1 bars, applies Wilder's smoothing (alpha = 1 / period).
    For shorter histories with at least 2 points, calculates RSI over all available deltas.
    """
    if hist.empty or len(hist) < 2:
        return pd.NA

    delta = hist["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    if len(hist) < period + 1:
        # Compute over all available deltas (skipping initial NaN)
        avg_gain = gain.iloc[1:].mean()
        avg_loss = loss.iloc[1:].mean()
    else:
        # Standard Wilder's exponential smoothing
        avg_gain = (
            gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False)
            .mean()
            .iloc[-1]
        )
        avg_loss = (
            loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False)
            .mean()
            .iloc[-1]
        )

    if pd.isna(avg_gain) or pd.isna(avg_loss):
        return pd.NA
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else pd.NA
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# ── Primary Symbol Fallback Registry ──────────────────────────────────────

PRIMARY_SYMBOL_MAP = {
    # Royal Gold
    "FRA:RYL": "RGLD",
    "RYL.F": "RGLD",
    "RYL": "RGLD",
    # Franco-Nevada
    "FRA:R5A": "FNV",
    "R5A.F": "FNV",
    "R5A": "FNV",
    # Wheaton Precious Metals
    "FRA:WPM": "WPM",
    "WPM.F": "WPM",
    "WPM.L": "WPM",
    # Triple Flag
    "FRA:TFPM": "TFPM",
    "TFPM.F": "TFPM",
    # Sandstorm Gold
    "TSX:SSL": "SAND",
    "SSL.TO": "SAND",
    # Vox Royalties
    "CVE:VOX": "VOXR",
    "VOX.V": "VOXR",
    # Metalla
    "TSX:MTA": "MTA",
    "MTA.TO": "MTA",
}


def _enrich_stock_info(
    original_ticker: str,
    yahoo_symbol: str,
    info: dict,
    ticker_obj: yf.Ticker | None = None,
) -> dict:
    """
    Enrich `info` dictionary with missing valuation/metric fields using:
    1. Primary symbol mapping (e.g. RYL.F -> RGLD, R5A.F -> FNV, WPM.F -> WPM, TFPM.F -> TFPM)
    2. Primary ticker resolution by stripping regional exchange suffixes (.F, .DE, .V, .L, etc.)
    """
    enriched = dict(info) if isinstance(info, dict) else {}

    primary_symbol = PRIMARY_SYMBOL_MAP.get(original_ticker) or PRIMARY_SYMBOL_MAP.get(
        yahoo_symbol
    )

    if not primary_symbol and "." in yahoo_symbol:
        base = yahoo_symbol.split(".")[0]
        if base in PRIMARY_SYMBOL_MAP:
            primary_symbol = PRIMARY_SYMBOL_MAP[base]
        elif len(base) >= 3 and not base.isdigit():
            primary_symbol = base

    if primary_symbol and primary_symbol != yahoo_symbol:
        try:
            p_obj = yf.Ticker(primary_symbol)
            p_info = p_obj.info
            if p_info:
                for key, val in p_info.items():
                    if val is not None and (
                        enriched.get(key) is None or enriched.get(key) == "N/A"
                    ):
                        enriched[key] = val
        except Exception as e:
            logger.debug(
                f"Primary symbol fallback fetch failed for {primary_symbol}: {e}",
                exc_info=True,
            )

    return enriched


def _calculate_pe_ratio(
    info: dict, curr_p: float, ticker_obj: yf.Ticker | None = None
) -> float | Any:
    """Calculate Price-to-Earnings ratio with multiple fallbacks."""
    if pd.isna(curr_p):
        return pd.NA

    # 1. Trailing P/E
    pe_v = info.get("trailingPE")
    if (
        pe_v is not None
        and pe_v != "None"
        and isinstance(pe_v, (int, float))
        and pe_v > 0
    ):
        return pe_v

    # 2. Forward P/E
    pe_v = info.get("forwardPE")
    if (
        pe_v is not None
        and pe_v != "None"
        and isinstance(pe_v, (int, float))
        and pe_v > 0
    ):
        return pe_v

    # 3. Trailing or Forward EPS
    eps = info.get("trailingEps") or info.get("forwardEps")
    if eps and isinstance(eps, (int, float)) and eps > 0:
        price = curr_p
        # Normalize GBp (pence) to GBP if financial currency is GBP
        curr = info.get("currency", "")
        fin_curr = info.get("financialCurrency", "")
        if curr == "GBp" and fin_curr == "GBP":
            price = curr_p / 100.0
        return price / eps

    # 4. Quarterly financial statement TTM calculation
    if ticker_obj is not None:
        try:
            q_inc = ticker_obj.quarterly_financials
            if not q_inc.empty and "Net Income" in q_inc.index:
                ttm_net = q_inc.loc["Net Income"].head(4).sum()
                mkt_cap = info.get("marketCap")
                if mkt_cap and isinstance(mkt_cap, (int, float)) and ttm_net > 0:
                    return mkt_cap / ttm_net
        except Exception:
            logger.debug(
                "Quarterly financial statement TTM calculation failed",
                exc_info=True,
            )

    return pd.NA


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
    """Determine valuation label based on P/E, PEG ratios, or fallback P/S / P/B ratios."""
    if isinstance(pe_v, (int, float)) and not pd.isna(pe_v) and pe_v > 0:
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

    # Fallback Tier 1: Price-to-Sales (P/S) ratio when P/E is uncomputed/missing
    ps_v = info.get("priceToSalesTrailing12Months")
    if ps_v is not None and isinstance(ps_v, (int, float)) and ps_v > 0:
        if ps_v <= 3.0:
            return "Cheap (P/S)"
        elif ps_v <= 8.0:
            return "Fair (P/S)"
        else:
            return "Expensive (P/S)"

    # Fallback Tier 2: Price-to-Book (P/B) ratio
    pb_v = info.get("priceToBook")
    if pb_v is not None and isinstance(pb_v, (int, float)) and pb_v > 0:
        if pb_v <= 1.5:
            return "Cheap (P/B)"
        elif pb_v <= 4.0:
            return "Fair (P/B)"
        else:
            return "Expensive (P/B)"

    return "N/A"


def _determine_trend_status(curr_p, sma200, sma50, rsi, pe_v, kgv_max: int) -> str:
    """
    Determine trend signal using SMA200, SMA50, RSI and P/E.
    Signals: STRONG BUY | BULLISH | OVERBOUGHT | HOLD | BEARISH
    """
    if pd.isna(curr_p) or pd.isna(sma200):
        return "HOLD"

    above_sma200 = curr_p > sma200
    # Golden cross alignment: Price > SMA50 >= SMA200, with valid P/E below threshold
    golden_cross = (
        (not pd.isna(sma50))
        and (curr_p > sma50)
        and (sma50 >= sma200)
        and (not pd.isna(pe_v))
    )
    rsi_ok = pd.isna(rsi) or (30 <= rsi <= 70)
    rsi_overbought = (not pd.isna(rsi)) and rsi > 70
    rsi_oversold = (not pd.isna(rsi)) and rsi < 30
    pe_ok = pd.isna(pe_v) or (isinstance(pe_v, (int, float)) and pe_v < kgv_max)

    if above_sma200 and golden_cross and rsi_ok and pe_ok:
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


# ── Known Royalty & Streaming Tickers & Keywords ──────────────────────────

ROYALTY_STREAMING_REGISTRY = {
    # Franco-Nevada
    "FNV",
    "FNV.TO",
    "NYSE:FNV",
    "TSX:FNV",
    "FRA:R5A",
    "R5A.F",
    # Wheaton Precious Metals
    "WPM",
    "WPM.TO",
    "NYSE:WPM",
    "TSX:WPM",
    "LSE:WPM",
    "WPM.L",
    "FRA:WPM",
    # Royal Gold
    "RGLD",
    "NASDAQ:RGLD",
    "FRA:RYL",
    "RYL.F",
    "RYL",
    # Triple Flag Precious Metals
    "TFPM",
    "TFPM.TO",
    "NYSE:TFPM",
    "TSX:TFPM",
    # Osisko Gold Royalties
    "OR",
    "OR.TO",
    "NYSE:OR",
    "TSX:OR",
    # Sandstorm Gold Royalties
    "SAND",
    "SSL.TO",
    "NYSE:SAND",
    "TSX:SSL",
    # Vox Royalties
    "VOXR",
    "VOXR.TO",
    "NASDAQ:VOXR",
    "TSX:VOXR",
    "VOX.V",
    "CVE:VOX",
    "VOX",
    # Metalla Royalty & Streaming
    "MTA",
    "MTA.TO",
    "NYSE:MTA",
    "TSX:MTA",
    # Altius Minerals
    "ALS.TO",
    "TSX:ALS",
    "ALS",
    # Freehold Royalties
    "FRU.TO",
    "TSX:FRU",
    "FRU",
    # Lithium Royalty Corp
    "LRC.TO",
    "TSX:LRC",
    "LRC",
    # Ecora Resources (Anglo Pacific Group)
    "ECOR.L",
    "LSE:ECOR",
    "ECOR",
    # EMX Royalty
    "EMX",
    "EMX.TO",
    "NYSE:EMX",
    "TSX:EMX",
    # Elemental Altus Royalties
    "ELE.V",
    "CVE:ELE",
    "ELE",
    # Star Royalties
    "STRR.V",
    "CVE:STRR",
    # Orogen Royalties
    "OGN.V",
    "CVE:OGN",
}

ROYALTY_COMPANY_NAMES = [
    "royal gold",
    "franco-nevada",
    "franco nevada",
    "wheaton precious",
    "triple flag",
    "vox royalties",
    "vox royalty",
    "osisko gold royalties",
    "osisko gold",
    "sandstorm gold",
    "metalla royalty",
    "altius minerals",
    "freehold royalties",
    "lithium royalty",
    "ecora resources",
    "deterra royalties",
    "emx royalty",
    "elemental altus",
    "star royalties",
    "orogen royalties",
]

ROYALTY_KEYWORDS = [
    "royalty",
    "royalties",
    "streaming company",
    "streaming agreements",
    "stream agreement",
    "net smelter return",
    "nsr",
    "gross revenue royalty",
    "precious metals stream",
    "purchase agreements to acquire",
    "free cash flow streaming",
]


def determine_business_model(
    original_ticker: str = "", yahoo_symbol: str = "", info: dict | None = None
) -> str:
    """
    Determine the business model:
    - 'Royalty & Streaming': Non-operating resource capital providers receiving streams/NSR.
    - 'Operating Miner': Mining operators in Basic Materials / Energy.
    - 'Operating Company': General non-resource operating firms.
    - 'N/A': Missing metadata or empty input.
    """
    if info is None:
        info = {}

    orig_clean = (original_ticker or "").upper().strip()
    yahoo_clean = (yahoo_symbol or "").upper().strip()
    base_symbol = yahoo_clean.split(".")[0] if yahoo_clean else ""

    orig_lower = (original_ticker or "").lower().strip()
    company_name = (
        (info.get("longName") or info.get("shortName") or "").lower()
        if isinstance(info, dict)
        else ""
    )

    # 1. Check curated ticker registry
    if (
        orig_clean in ROYALTY_STREAMING_REGISTRY
        or yahoo_clean in ROYALTY_STREAMING_REGISTRY
        or (base_symbol and base_symbol in ROYALTY_STREAMING_REGISTRY)
    ):
        return "Royalty & Streaming"

    # 2. Check known company names and phrases
    if any(name in orig_lower for name in ROYALTY_COMPANY_NAMES) or any(
        name in company_name for name in ROYALTY_COMPANY_NAMES
    ):
        return "Royalty & Streaming"

    # 3. NLP check on company summary, industry, and name
    summary = (
        (info.get("longBusinessSummary") or "").lower()
        if isinstance(info, dict)
        else ""
    )
    industry = (info.get("industry") or "").lower() if isinstance(info, dict) else ""
    sector = (info.get("sector") or "").lower() if isinstance(info, dict) else ""

    if (
        any(kw in summary for kw in ROYALTY_KEYWORDS)
        or "royalty" in industry
        or "streaming" in industry
        or "royalty" in company_name
        or "royalties" in company_name
    ):
        return "Royalty & Streaming"

    # 3. Basic Materials / Metals & Mining heuristic vs general operating company
    if (
        sector in ["basic materials", "energy"]
        or "mining" in industry
        or "precious metals" in industry
        or "gold" in industry
        or "silver" in industry
    ):
        return "Operating Miner"

    if sector or industry or company_name:
        return "Operating Company"

    return "N/A"


def determine_primary_commodity(info: dict | None = None) -> dict[str, str]:
    """
    Detect primary commodity and broad commodity category from industry, sector,
    and business description.
    """
    if not isinstance(info, dict) or not info:
        return {"Commodity": "N/A", "Commodity Category": "N/A"}

    industry = (info.get("industry") or "").lower().strip()
    sector = (info.get("sector") or "").lower().strip()
    summary = (info.get("longBusinessSummary") or "").lower()
    name = (info.get("longName") or info.get("shortName") or "").lower()
    text = f"{industry} {name} {summary}"

    # 1. Precious Metals
    if "gold" in industry or re.search(r"\bgold\b", text):
        return {"Commodity": "Gold", "Commodity Category": "Precious Metals"}
    if "silver" in industry or re.search(r"\bsilver\b", text):
        return {"Commodity": "Silver", "Commodity Category": "Precious Metals"}
    if re.search(r"\b(platinum|palladium|pgm|rhodium)\b", text):
        return {"Commodity": "PGM", "Commodity Category": "Precious Metals"}

    # 2. Critical & Energy Transition Metals
    if "uranium" in industry or re.search(r"\b(uranium|u3o8|yellowcake)\b", text):
        return {"Commodity": "Uranium", "Commodity Category": "Critical Metals"}
    if "copper" in industry or re.search(r"\bcopper\b", text):
        return {"Commodity": "Copper", "Commodity Category": "Critical Metals"}
    if re.search(r"\b(lithium|spodumene|brine)\b", text):
        return {"Commodity": "Lithium", "Commodity Category": "Critical Metals"}
    if re.search(r"\bnickel\b", text):
        return {"Commodity": "Nickel", "Commodity Category": "Critical Metals"}
    if re.search(r"\bcobalt\b", text):
        return {"Commodity": "Cobalt", "Commodity Category": "Critical Metals"}
    if re.search(r"\b(rare earth|ree|neodymium|praseodymium|dysprosium)\b", text):
        return {"Commodity": "Rare Earths", "Commodity Category": "Critical Metals"}
    if re.search(r"\bgraphite\b", text):
        return {"Commodity": "Graphite", "Commodity Category": "Critical Metals"}

    # 3. Base & Industrial Metals
    if "aluminum" in industry or re.search(r"\b(aluminum|bauxite)\b", text):
        return {"Commodity": "Aluminum", "Commodity Category": "Base Metals"}
    if re.search(r"\b(iron ore|hematite|magnetite|iron ore pellet)\b", text):
        return {"Commodity": "Iron Ore", "Commodity Category": "Base Metals"}
    if re.search(r"\b(zinc|lead)\b", text):
        return {"Commodity": "Zinc & Lead", "Commodity Category": "Base Metals"}
    if "steel" in industry or re.search(r"\bsteel\b", text):
        return {"Commodity": "Steel", "Commodity Category": "Base Metals"}

    # 4. Energy & Bulks
    if "coal" in industry or re.search(
        r"\b(thermal coal|metallurgical coal|coking coal)\b", text
    ):
        return {"Commodity": "Coal", "Commodity Category": "Bulks & Energy"}
    if re.search(r"\b(potash|phosphate|fertilizer)\b", text):
        return {
            "Commodity": "Fertilizers / Potash",
            "Commodity Category": "Bulks & Energy",
        }

    # 5. Generic mining / resources
    if (
        sector in ["basic materials", "energy"]
        or "mining" in industry
        or "metals" in industry
        or "mineral" in text
    ):
        return {
            "Commodity": "Diversified Mining",
            "Commodity Category": "Diversified Resources",
        }

    return {"Commodity": "Non-Resource", "Commodity Category": "Non-Resource"}


def determine_mining_lifecycle(
    original_ticker: str = "",
    yahoo_symbol: str = "",
    info: dict | None = None,
    business_model: str | None = None,
) -> str:
    """
    Determine the mining lifecycle stage along the Lassonde Curve:
    - 'Royalty & Streaming': Non-operating capital providers receiving NSR / streams.
    - 'Junior Explorer': Pre-revenue or exploration/drilling stage.
    - 'Developer': Feasibility, permitting, or mine construction stage.
    - 'Producer': Active commercial mining with meaningful revenue or operating cashflow.
    - 'Non-Mining': Companies outside Basic Materials / Mining.
    - 'N/A': Missing metadata.
    """
    if info is None:
        info = {}

    if business_model is None:
        business_model = determine_business_model(original_ticker, yahoo_symbol, info)

    if business_model == "Royalty & Streaming":
        return "Royalty & Streaming"

    industry = (info.get("industry") or "").lower()
    sector = (info.get("sector") or "").lower()
    summary = (info.get("longBusinessSummary") or "").lower()
    name = (info.get("longName") or info.get("shortName") or "").lower()

    is_resource = (
        business_model == "Operating Miner"
        or sector in ["basic materials", "energy"]
        or any(
            k in industry
            for k in ["mining", "metals", "gold", "silver", "copper", "uranium"]
        )
        or any(
            k in name
            for k in [
                "gold",
                "silver",
                "mining",
                "minerals",
                "resources",
                "metals",
                "exploration",
            ]
        )
    )

    if not is_resource:
        return "Non-Mining" if (sector or industry or name) else "N/A"

    rev = info.get("totalRevenue")
    ocf = info.get("operatingCashflow")
    fcf = info.get("freeCashflow")

    # Has significant commercial revenue (> $25M) or high positive OCF (> $10M)
    has_commercial_production = (
        isinstance(rev, (int, float)) and rev >= 25_000_000
    ) or (isinstance(ocf, (int, float)) and ocf >= 10_000_000)

    # Keywords indicative of developers
    developer_keywords = [
        "development stage",
        "under development",
        "feasibility study",
        "pre-feasibility",
        "preliminary economic assessment",
        "definitive feasibility",
        "construction of",
        "mine construction",
        "permitting phase",
        "mine development",
        "in-construction",
    ]
    is_dev_text = any(kw in summary for kw in developer_keywords)

    # Keywords indicative of junior exploration
    explorer_keywords = [
        "exploration stage",
        "exploration company",
        "exploration and evaluation",
        "mineral exploration",
        "exploration of mineral properties",
        "prospecting",
        "drill program",
        "drilling program",
        "early stage exploration",
        "greenfield",
    ]
    is_exp_text = any(kw in summary for kw in explorer_keywords)

    if has_commercial_production and not is_dev_text:
        return "Producer"

    if is_dev_text or (
        isinstance(fcf, (int, float))
        and fcf < -50_000_000
        and not has_commercial_production
    ):
        return "Developer"

    if (
        is_exp_text
        or (isinstance(rev, (int, float)) and rev < 10_000_000)
        or rev is None
        or rev == 0
    ):
        return "Junior Explorer"

    if has_commercial_production:
        return "Producer"

    return "Developer" if is_dev_text else "Junior Explorer"


def calculate_cash_runway(info: dict | None = None) -> dict[str, Any]:
    """
    Calculate cash reserves, annual cash burn rate, cash runway (months),
    dilution risk, and cash backing percentages.
    """
    _empty = {
        "Total Cash": pd.NA,
        "Total Debt": pd.NA,
        "Net Cash": pd.NA,
        "Annual Cash Burn": pd.NA,
        "Cash Runway (Mos)": pd.NA,
        "Dilution Risk": "N/A",
        "Cash Backing (%)": pd.NA,
        "Net Cash Backing (%)": pd.NA,
    }
    if not isinstance(info, dict) or not info:
        return _empty

    cash = info.get("totalCash")
    debt = info.get("totalDebt")
    ocf = info.get("operatingCashflow")
    fcf = info.get("freeCashflow")
    mcap = info.get("marketCap")

    cash_val = (
        float(cash) if isinstance(cash, (int, float)) and not pd.isna(cash) else None
    )
    debt_val = (
        float(debt) if isinstance(debt, (int, float)) and not pd.isna(debt) else 0.0
    )

    net_cash_val = (cash_val - debt_val) if cash_val is not None else None

    # Calculate annual cash burn
    annual_burn = None
    if isinstance(fcf, (int, float)) and fcf < 0:
        annual_burn = abs(float(fcf))
    elif isinstance(ocf, (int, float)) and ocf < 0:
        annual_burn = abs(float(ocf))
    elif (isinstance(fcf, (int, float)) and fcf >= 0) or (
        isinstance(ocf, (int, float)) and ocf >= 0
    ):
        annual_burn = 0.0

    # Cash runway in months
    runway_mos = pd.NA
    dilution_risk = "N/A"

    if annual_burn is not None:
        if annual_burn == 0.0:
            dilution_risk = "Low (Cash Flow +)"
        elif cash_val is not None and cash_val > 0:
            months = round((cash_val / annual_burn) * 12, 1)
            runway_mos = months
            if months >= 36.0:
                dilution_risk = "Low (> 36 mos)"
            elif months >= 12.0:
                dilution_risk = "Moderate (12–36 mos)"
            else:
                dilution_risk = "High (< 12 mos)"
        else:
            runway_mos = 0.0
            dilution_risk = "High (< 12 mos)"

    # Cash backing % of market cap
    cash_backing_pct = pd.NA
    net_cash_backing_pct = pd.NA
    if isinstance(mcap, (int, float)) and mcap > 0:
        if cash_val is not None:
            cash_backing_pct = round((cash_val / mcap) * 100, 1)
        if net_cash_val is not None:
            net_cash_backing_pct = round((net_cash_val / mcap) * 100, 1)

    return {
        "Total Cash": cash_val if cash_val is not None else pd.NA,
        "Total Debt": debt_val if debt is not None else pd.NA,
        "Net Cash": net_cash_val if net_cash_val is not None else pd.NA,
        "Annual Cash Burn": annual_burn if annual_burn is not None else pd.NA,
        "Cash Runway (Mos)": runway_mos,
        "Dilution Risk": dilution_risk,
        "Cash Backing (%)": cash_backing_pct,
        "Net Cash Backing (%)": net_cash_backing_pct,
    }


def _get_optional_metrics(
    info: dict,
    include_dividend: bool | None = None,
    include_market_cap: bool | None = None,
    original_ticker: str = "",
    yahoo_symbol: str = "",
) -> dict:
    """Fetch optional metrics: dividend yield, market cap, D/E, growth, margin, beta, sector, business model, lifecycle, commodity, cash runway."""
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

    # Business Model
    biz_model = determine_business_model(original_ticker, yahoo_symbol, info)
    result["Business Model"] = biz_model

    # Mining & Resource Taxonomy
    lifecycle = determine_mining_lifecycle(
        original_ticker, yahoo_symbol, info, business_model=biz_model
    )
    result["Mining Lifecycle"] = lifecycle

    comm_info = determine_primary_commodity(info)
    result["Commodity"] = comm_info["Commodity"]
    result["Commodity Category"] = comm_info["Commodity Category"]

    # Simply Wall St style Cash Runway & Dilution Risk
    runway_data = calculate_cash_runway(info)
    result.update(runway_data)

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


# ── Analyst consensus & Buy score calculations ──────────────────────────────


def _get_analyst_metrics(info: dict, curr_p: float) -> dict:
    """Fetch analyst consensus target price, upside potential, and recommendation."""
    target_mean = info.get("targetMeanPrice")
    rec_key = info.get("recommendationKey")
    num_analysts = info.get("numberOfAnalystOpinions")

    result = {
        "Target Price": pd.NA,
        "Target Upside (%)": pd.NA,
        "Recommendation": "N/A",
    }

    if (
        target_mean is not None
        and isinstance(target_mean, (int, float))
        and target_mean > 0
    ):
        result["Target Price"] = round(float(target_mean), 2)
        if not pd.isna(curr_p) and curr_p > 0:
            upside = ((target_mean - curr_p) / curr_p) * 100
            result["Target Upside (%)"] = round(upside, 1)

    if rec_key and isinstance(rec_key, str) and rec_key != "none":
        rec_clean = rec_key.replace("_", " ").title()
        if num_analysts and isinstance(num_analysts, int) and num_analysts > 0:
            result["Recommendation"] = f"{rec_clean} ({num_analysts})"
        else:
            result["Recommendation"] = rec_clean

    return result


def _calculate_buy_score(metrics: dict) -> tuple[int, str, list[str], list[str]]:
    """
    Compute a composite 0-100 Buying Opportunity Score, rating label,
    and lists of identified strengths and risk flags.

    Pillars (25 pts each):
    1. Valuation (P/E, PEG, P/S, P/B)
    2. Trend & Momentum (SMA200, SMA50, Golden Cross, RSI)
    3. Financial Health (Debt/Equity, Profit Margin, Revenue Growth)
    4. Catalysts & Margin of Safety (Analyst Upside, Recommendation, 52W Low proximity)
    """
    score = 0
    strengths = []
    risks = []

    pe = metrics.get("P/E (KGV)")
    val_status = str(metrics.get("Valuation", ""))
    trend = str(metrics.get("Trend", ""))
    rsi = metrics.get("RSI")
    de = metrics.get("D/E Ratio")
    margin = metrics.get("Profit Margin (%)")
    growth = metrics.get("Revenue Growth (%)")
    upside = metrics.get("Target Upside (%)")
    rec = str(metrics.get("Recommendation", ""))
    w52_low = metrics.get("52W Low (%)")

    # ── 1. Valuation (max 25 pts) ──
    val_pts = 0
    if isinstance(pe, (int, float)) and not pd.isna(pe) and pe > 0:
        if pe <= 15:
            val_pts += 18
            strengths.append(f"Low P/E multiple ({pe:.1f})")
        elif pe <= 25:
            val_pts += 12
        elif pe <= 35:
            val_pts += 5
        else:
            risks.append(f"Elevated P/E multiple ({pe:.1f})")

        if "PEG" in val_status:
            if "Very Cheap" in val_status or "Good PEG" in val_status:
                val_pts += 7
                strengths.append("Attractive PEG growth ratio")
            elif "High PEG" in val_status:
                risks.append("High PEG ratio relative to growth")
    elif "Cheap" in val_status:
        val_pts += 15
        strengths.append("Favorable asset/sales valuation")
    elif "Fair" in val_status:
        val_pts += 10
    score += min(25, val_pts)

    # ── 2. Trend & Momentum (max 25 pts) ──
    trend_pts = 0
    if trend == "STRONG BUY":
        trend_pts += 25
        strengths.append("Strong Golden Cross trend alignment")
    elif trend == "BULLISH":
        trend_pts += 18
        strengths.append("Trading above 200-day moving average")
    elif trend == "OVERSOLD":
        trend_pts += 12
        strengths.append("Oversold technical bounce potential")
    elif trend == "HOLD":
        trend_pts += 8
    elif trend == "BEARISH":
        risks.append("Downtrend below 200-day moving average")

    if isinstance(rsi, (int, float)) and not pd.isna(rsi):
        if 30 <= rsi <= 55:
            trend_pts += 5
        elif rsi > 70:
            risks.append(f"Overbought RSI ({rsi:.1f})")
    score += min(25, trend_pts)

    # ── 3. Financial Health & Quality (max 25 pts) ──
    health_pts = 0
    if isinstance(de, (int, float)) and not pd.isna(de):
        if de <= 0.8:
            health_pts += 10
            strengths.append(f"Conservative debt profile (D/E {de:.2f})")
        elif de <= 1.5:
            health_pts += 6
        else:
            risks.append(f"Elevated debt-to-equity ({de:.2f})")

    if isinstance(margin, (int, float)) and not pd.isna(margin):
        if margin >= 20.0:
            health_pts += 10
            strengths.append(f"High profit margin ({margin:.1f}%)")
        elif margin >= 8.0:
            health_pts += 6
        elif margin < 0:
            risks.append(f"Negative profit margin ({margin:.1f}%)")

    if isinstance(growth, (int, float)) and not pd.isna(growth):
        if growth >= 15.0:
            health_pts += 5
            strengths.append(f"Strong YoY revenue expansion ({growth:.1f}%)")
        elif growth >= 0:
            health_pts += 3
        else:
            risks.append(f"Contracting revenue ({growth:.1f}%)")
    score += min(25, health_pts)

    # ── 4. Catalysts & Margin of Safety (max 25 pts) ──
    cat_pts = 0
    if isinstance(upside, (int, float)) and not pd.isna(upside):
        if upside >= 30.0:
            cat_pts += 15
            strengths.append(f"Significant analyst upside (+{upside:.1f}%)")
        elif upside >= 15.0:
            cat_pts += 10
            strengths.append(f"Moderate analyst upside (+{upside:.1f}%)")
        elif upside > 0:
            cat_pts += 5
        else:
            risks.append(f"Trading above analyst target ({upside:.1f}%)")

    if any(k in rec.lower() for k in ["strong buy", "buy"]):
        cat_pts += 10
        strengths.append(f"Consensus recommendation: {rec}")

    if isinstance(w52_low, (int, float)) and not pd.isna(w52_low) and w52_low <= 10.0:
        cat_pts += 5
        strengths.append("Trading near 52-week support")
    score += min(25, cat_pts)

    # ── Value Trap Detection ──
    is_value_trap = False
    if "Cheap" in val_status and trend in ["BEARISH", "HOLD"]:
        red_flags = 0
        if isinstance(de, (int, float)) and not pd.isna(de) and de > 2.0:
            red_flags += 1
        if isinstance(margin, (int, float)) and not pd.isna(margin) and margin < 0:
            red_flags += 1
        if isinstance(growth, (int, float)) and not pd.isna(growth) and growth < -10.0:
            red_flags += 1
        if red_flags >= 1:
            is_value_trap = True
            risks.insert(
                0,
                "⚠️ Value Trap Risk: Low valuation accompanied by weak fundamentals & downtrend",
            )
            score = max(0, score - 20)

    # ── Mining & Dilution Risk Adjustments ──
    dilution = str(metrics.get("Dilution Risk", ""))
    runway = metrics.get("Cash Runway (Mos)")
    net_cash_pct = metrics.get("Net Cash Backing (%)")

    if dilution.startswith("High"):
        if isinstance(runway, (int, float)) and not pd.isna(runway):
            risks.insert(
                0, f"⚠️ High Dilution Risk: Cash runway < 12 mos ({runway:.0f} mos)"
            )
        else:
            risks.insert(0, "⚠️ High Dilution Risk: Cash runway < 12 mos")
        score = max(0, score - 15)
    elif isinstance(runway, (int, float)) and not pd.isna(runway) and runway >= 24.0:
        strengths.append(f"Strong cash runway ({runway:.0f} mos)")

    if (
        isinstance(net_cash_pct, (int, float))
        and not pd.isna(net_cash_pct)
        and net_cash_pct >= 20.0
    ):
        strengths.append(
            f"Significant net cash backing ({net_cash_pct:.1f}% of market cap)"
        )

    # Overall Opportunity Rating
    if is_value_trap:
        rating = "Value Trap Risk"
    elif score >= 75:
        rating = "Top Opportunity"
    elif score >= 60:
        rating = "Good Opportunity"
    elif score >= 40:
        rating = "Watchlist"
    else:
        rating = "Unfavorable"

    return score, rating, strengths, risks


def calculate_snowflake_scores(metrics: dict) -> dict[str, Any]:
    """
    Calculate 5-pillar Simply Wall St style scores (0-6 each):
    - Value (0-6): P/E multiple, PEG/Valuation status, Net Cash Backing, and Target Upside.
    - Future (0-6): Revenue growth, consensus recommendation, and analyst upside.
    - Past (0-6): Operating profit margins, dual-SMA trend momentum, and 52W high proximity.
    - Health (0-6): Balance sheet leverage (D/E), Cash Runway (for explorers), operating profitability, and beta.
    - Dividend (0-6): Dividend yield and payout sustainability from net margin.
    Total: 0-30 points.
    """
    scores = {"Value": 0, "Future": 0, "Past": 0, "Health": 0, "Dividend": 0}

    lifecycle = str(metrics.get("Mining Lifecycle", ""))
    pe = metrics.get("P/E (KGV)")
    val = str(metrics.get("Valuation", ""))
    upside = metrics.get("Target Upside (%)")
    rev_growth = metrics.get("Revenue Growth (%)")
    rec = str(metrics.get("Recommendation", "")).lower()
    margin = metrics.get("Profit Margin (%)")
    trend = str(metrics.get("Trend", ""))
    w52_high = metrics.get("52W High (%)")
    biz_model = str(metrics.get("Business Model", ""))
    de = metrics.get("D/E Ratio")
    beta = metrics.get("Beta")
    div_yield = metrics.get("Dividend Yield (%)")

    # ── Tailored evaluation for pre-revenue Junior Explorers & Developers ──
    if lifecycle in ["Junior Explorer", "Developer"]:
        # 1. Value (0-6): Net Cash backing & Target Upside
        v_pts = 0
        net_cash_pct = metrics.get("Net Cash Backing (%)")
        if isinstance(net_cash_pct, (int, float)) and not pd.isna(net_cash_pct):
            if net_cash_pct >= 25.0:
                v_pts += 3
            elif net_cash_pct >= 10.0:
                v_pts += 2
            elif net_cash_pct > 0:
                v_pts += 1

        if isinstance(upside, (int, float)) and not pd.isna(upside):
            if upside >= 30.0:
                v_pts += 2
            elif upside >= 15.0:
                v_pts += 1

        if "Cheap" in val:
            v_pts += 1
        scores["Value"] = min(6, v_pts)

        # 2. Future (0-6): Discovery potential, Analyst Target Upside & Recommendation
        f_pts = 0
        if isinstance(upside, (int, float)) and not pd.isna(upside):
            if upside >= 35.0:
                f_pts += 3
            elif upside >= 15.0:
                f_pts += 2
            elif upside > 0:
                f_pts += 1

        if any(k in rec for k in ["strong buy", "buy"]):
            f_pts += 2
        elif "hold" in rec:
            f_pts += 1

        if trend in ["STRONG BUY", "BULLISH"]:
            f_pts += 1
        scores["Future"] = min(6, f_pts)

        # 3. Past / Momentum (0-6): Dual-SMA trend alignment & 52W high proximity
        p_pts = 0
        if trend in ["STRONG BUY", "BULLISH"]:
            p_pts += 3
        elif trend == "HOLD":
            p_pts += 1

        if isinstance(w52_high, (int, float)) and not pd.isna(w52_high):
            if w52_high >= -15.0:
                p_pts += 2
            elif w52_high >= -35.0:
                p_pts += 1

        if isinstance(margin, (int, float)) and not pd.isna(margin) and margin > 0:
            p_pts += 1
        scores["Past"] = min(6, p_pts)

        # 4. Financial Health (0-6): Cash Runway, Net Cash & Low Debt Overhang
        h_pts = 0
        runway = metrics.get("Cash Runway (Mos)")
        dilution_r = str(metrics.get("Dilution Risk", ""))
        if isinstance(runway, (int, float)) and not pd.isna(runway):
            if runway >= 24.0:
                h_pts += 3
            elif runway >= 12.0:
                h_pts += 2
            elif runway >= 6.0:
                h_pts += 1
        elif "Cash Flow +" in dilution_r:
            h_pts += 3

        net_cash = metrics.get("Net Cash")
        if (
            isinstance(net_cash, (int, float))
            and not pd.isna(net_cash)
            and net_cash > 0
        ):
            h_pts += 2

        if isinstance(de, (int, float)) and not pd.isna(de) and de <= 0.3:
            h_pts += 1
        if isinstance(beta, (int, float)) and not pd.isna(beta) and beta <= 1.2:
            h_pts += 1
        scores["Health"] = min(6, h_pts)

        # 5. Dividend (0-6): 0 for early stage exploration/development
        scores["Dividend"] = 0
        scores["Total"] = sum(scores.values())
        return scores

    # ── Standard evaluation for Producers, Royalty & Operating Companies ──
    # ── 1. Value (0-6) ──
    v_pts = 0
    if "Cheap" in val:
        v_pts += 3
    elif "Fair" in val:
        v_pts += 2
    elif "Expensive" in val:
        v_pts += 0
    else:
        v_pts += 1

    if isinstance(pe, (int, float)) and not pd.isna(pe):
        if 0 < pe <= 15:
            v_pts += 2
        elif 15 < pe <= 25:
            v_pts += 1

    if isinstance(upside, (int, float)) and not pd.isna(upside) and upside >= 15:
        v_pts += 1
    scores["Value"] = min(6, v_pts)

    # ── 2. Future Growth (0-6) ──
    f_pts = 0
    if isinstance(rev_growth, (int, float)) and not pd.isna(rev_growth):
        if rev_growth >= 20:
            f_pts += 3
        elif rev_growth >= 10:
            f_pts += 2
        elif rev_growth > 0:
            f_pts += 1

    if any(k in rec for k in ["strong buy", "buy"]):
        f_pts += 2
    elif "hold" in rec:
        f_pts += 1

    if isinstance(upside, (int, float)) and not pd.isna(upside) and upside >= 25:
        f_pts += 1
    scores["Future"] = min(6, f_pts)

    # ── 3. Past Performance (0-6) ──
    p_pts = 0
    margin_threshold = 40.0 if biz_model == "Royalty & Streaming" else 15.0
    if isinstance(margin, (int, float)) and not pd.isna(margin):
        if margin >= margin_threshold:
            p_pts += 3
        elif margin >= (margin_threshold / 2):
            p_pts += 2
        elif margin > 0:
            p_pts += 1

    if trend in ["STRONG BUY", "BULLISH"]:
        p_pts += 2
    elif trend == "HOLD":
        p_pts += 1

    if isinstance(w52_high, (int, float)) and not pd.isna(w52_high) and w52_high >= -15:
        p_pts += 1
    scores["Past"] = min(6, p_pts)

    # ── 4. Financial Health (0-6) ──
    h_pts = 0
    if biz_model == "Royalty & Streaming":
        h_pts += 3
    elif isinstance(de, (int, float)) and not pd.isna(de):
        if de <= 0.4:
            h_pts += 3
        elif de <= 1.0:
            h_pts += 2
        elif de <= 1.8:
            h_pts += 1

    if isinstance(margin, (int, float)) and not pd.isna(margin) and margin > 0:
        h_pts += 2

    if isinstance(beta, (int, float)) and not pd.isna(beta) and beta <= 1.1:
        h_pts += 1
    scores["Health"] = min(6, h_pts)

    # ── 5. Dividend (0-6) ──
    d_pts = 0
    if isinstance(div_yield, (int, float)) and not pd.isna(div_yield) and div_yield > 0:
        if div_yield >= 4.0:
            d_pts += 4
        elif div_yield >= 2.0:
            d_pts += 3
        else:
            d_pts += 2
        if isinstance(margin, (int, float)) and not pd.isna(margin) and margin > 10:
            d_pts += 2
    scores["Dividend"] = min(6, d_pts)

    scores["Total"] = sum(
        scores[k] for k in ["Value", "Future", "Past", "Health", "Dividend"]
    )
    return scores


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
        "Buy Score": pd.NA,
        "Opportunity Rating": "N/A",
        "Snowflake Score": pd.NA,
        "Snowflake Details": {},
        "Target Price": pd.NA,
        "Target Upside (%)": pd.NA,
        "Recommendation": "N/A",
        "Currency": "N/A",
        "Price (EUR)": pd.NA,
        "52W High (%)": pd.NA,
        "52W Low (%)": pd.NA,
        "D/E Ratio": pd.NA,
        "Revenue Growth (%)": pd.NA,
        "Profit Margin (%)": pd.NA,
        "Beta": pd.NA,
        "Sector": "N/A",
        "Business Model": "N/A",
        "Mining Lifecycle": "N/A",
        "Commodity": "N/A",
        "Commodity Category": "N/A",
        "Total Cash": pd.NA,
        "Total Debt": pd.NA,
        "Net Cash": pd.NA,
        "Annual Cash Burn": pd.NA,
        "Cash Runway (Mos)": pd.NA,
        "Dilution Risk": "N/A",
        "Cash Backing (%)": pd.NA,
        "Net Cash Backing (%)": pd.NA,
        "Key Strengths": "",
        "Key Risks": "",
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
        logger.warning(f"[{original_ticker}] Info fetch failed: {e}", exc_info=True)
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
                logger.warning(
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
            valuation = _determine_valuation_status(
                pe_v, info, pe_cheap, pe_expensive, peg_max
            )
            trend = _determine_trend_status(
                curr_p, sma200, sma50, rsi_for_trend, pe_v, kgv_max
            )
            optional = _get_optional_metrics(
                info,
                include_dividend,
                include_marketcap,
                original_ticker,
                yahoo_symbol,
            )
            w52 = _get_52w_metrics(info, curr_p)
            analyst = _get_analyst_metrics(info, curr_p)

            interim = {
                "Price": curr_p,
                "P/E (KGV)": pe_v,
                "Valuation": valuation,
                "Trend": trend,
                "RSI": rsi_reported,
                **w52,
                **optional,
                **analyst,
            }
            buy_score, opp_rating, strengths, risks = _calculate_buy_score(interim)
            snowflake_metrics = {
                **interim,
                "Business Model": optional.get("Business Model", ""),
                "Mining Lifecycle": optional.get("Mining Lifecycle", ""),
            }
            snowflake = calculate_snowflake_scores(snowflake_metrics)

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
                "Buy Score": buy_score,
                "Opportunity Rating": opp_rating,
                "Snowflake Score": snowflake["Total"],
                "Snowflake Details": snowflake,
                **analyst,
                **w52,
                **optional,
                "Key Strengths": "; ".join(strengths),
                "Key Risks": "; ".join(risks),
                "Status": "OK",
            }
            return result

        except Exception as e:
            logger.exception(
                f"[{original_ticker}] Error attempt {attempt + 1}/{retries_local}"
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
        logger.warning("No tickers provided.")
        return pd.DataFrame()

    max_workers = config.getint("General", "max_workers", fallback=MAX_WORKERS)
    num_tickers = len(ticker_tuples_list)

    if max_workers > 1 and num_tickers > 1:
        workers = min(max_workers, num_tickers)
        logger.info(f"Analyzing {num_tickers} tickers in parallel ({workers} workers).")
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(
                tqdm(
                    executor.map(get_financial_metrics, ticker_tuples_list),
                    total=num_tickers,
                    desc="Processing tickers",
                )
            )
    else:
        logger.info(f"Analyzing {num_tickers} tickers (sequential).")
        results = []
        for ticker_tuple in tqdm(ticker_tuples_list, desc="Processing tickers"):
            res = get_financial_metrics(ticker_tuple)
            results.append(res)

    df = pd.DataFrame(results)

    sort_column = config.get("General", "sort_by_column", fallback=SORT_BY_COLUMN)
    sort_ascending = config.getboolean(
        "General", "sort_ascending", fallback=SORT_ASCENDING
    )
    alias_map = {
        "KGV": "P/E (KGV)",
        "PE": "P/E (KGV)",
        "P/E": "P/E (KGV)",
        "Score": "Buy Score",
        "BuyScore": "Buy Score",
        "Upside": "Target Upside (%)",
        "Ticker": "Original Ticker",
        "Symbol": "Yahoo Symbol",
    }
    if sort_column in alias_map:
        sort_column = alias_map[sort_column]

    if sort_column in df.columns:
        numeric_cols = [
            "Price",
            "Price (EUR)",
            "SMA200",
            "SMA50",
            "RSI",
            "P/E (KGV)",
            "Buy Score",
            "Target Price",
            "Target Upside (%)",
            "Dividend Yield (%)",
            "52W High (%)",
            "52W Low (%)",
            "D/E Ratio",
            "Revenue Growth (%)",
            "Profit Margin (%)",
            "Beta",
        ]
        try:
            df = df.sort_values(
                by=sort_column,
                ascending=sort_ascending,
                na_position="last",
                key=lambda col: (
                    pd.to_numeric(col, errors="coerce")
                    if col.name in numeric_cols
                    else col
                ),
            )
        except Exception:
            logger.debug(
                f"Custom sort failed for column '{sort_column}', falling back to default sort",
                exc_info=True,
            )
            df = df.sort_values(
                by=sort_column, ascending=sort_ascending, na_position="last"
            )
    else:
        logger.warning(f"Sort column '{sort_column}' not found.")

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
    except Exception:
        logger.exception(f"History fetch failed for {yahoo_symbol}")
        return pd.DataFrame()


def search_company(query: str) -> list[dict]:
    """
    Search Yahoo Finance for companies matching a name or ticker query.
    Returns a list of dicts with symbol, name, exchange, and type.
    """
    if not query or len(query.strip()) < 2:
        return []
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {
        "q": query.strip(),
        "lang": "en-US",
        "region": "US",
        "quotesCount": 10,
        "newsCount": 0,
        "enableFuzzyQuery": "false",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for q in data.get("quotes", []):
            if q.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND"):
                results.append(
                    {
                        "symbol": q.get("symbol", ""),
                        "name": (
                            q.get("longname")
                            or q.get("shortname")
                            or q.get("symbol", "")
                        ),
                        "exchange": q.get("exchDisp") or q.get("exchange", ""),
                        "type": q.get("quoteType", ""),
                    }
                )
        return results
    except Exception as e:
        logger.debug(f"Company search failed for '{query}': {e}", exc_info=True)
        return []
