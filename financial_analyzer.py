import yfinance as yf
import pandas as pd
import re
import configparser
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm  # Für die Fortschrittsanzeige

# --- Konfiguration des Loggers ---
logging.basicConfig(
    level=logging.INFO,  # Standard-Logging-Level
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Ausgabe auf die Konsole
        # logging.FileHandler("app.log") # Optional: Ausgabe in eine Datei
    ],
)

# --- Konfiguration laden (Modul-Ebene) ---
config = configparser.ConfigParser()
config.read("config.ini")

# Allgemeine Einstellungen
SMA_PERIOD = config.getint("General", "sma_period")
KGV_MAX_THRESHOLD = config.getint("General", "kgv_max_threshold")
MAX_WORKERS = config.getint("General", "max_workers")
HISTORY_PERIOD = config.get("General", "history_period")
RETRIES = config.getint("General", "retries")
RETRY_DELAY_SECONDS = config.getint("General", "retry_delay_seconds")
SORT_BY_COLUMN = config.get("General", "sort_by_column")
SORT_ASCENDING = config.getboolean("General", "sort_ascending")
ATH_ATL_THRESHOLD_PERCENT = config.getint("General", "ath_atl_threshold_percent")

# Neue Bewertungs-Einstellungen
PE_CHEAP_THRESHOLD = config.getfloat("General", "pe_cheap_threshold")
PE_EXPENSIVE_THRESHOLD = config.getfloat("General", "pe_expensive_threshold")
PEG_MAX_THRESHOLD = config.getfloat("General", "peg_max_threshold")

# Metrik-Einstellungen
INCLUDE_DIVIDEND_YIELD = config.getboolean("Metrics", "include_dividend_yield")
INCLUDE_MARKET_CAP = config.getboolean("Metrics", "include_market_cap")


def format_large_number(num):
    """
    Formatiert große Zahlen in ein menschenlesbares Format (z.B. 1.23B, 45.6M).
    """
    if not isinstance(num, (int, float)):
        return num

    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0

    return "%.2f%s" % (num, ["", "K", "M", "B", "T"][magnitude])


def parse_and_convert_tickers(data_string):
    """
    Extrahiert Symbole aus dem Rohdatenstring und konvertiert sie in das
    Yahoo Finance-kompatible Format.
    Gibt eine Liste von Tupeln zurück: (original_ticker, yahoo_ticker_symbol)
    """
    pattern = r"(?:FRA:|ETR:|CVE:|NASDAQ:)[A-Z0-9]+?(?=(?:FRA:|ETR:|CVE:|NASDAQ:)|[^A-Z0-9]|$)"
    raw_matches = re.findall(pattern, data_string)

    converted_tickers = []
    for t in raw_matches:
        original_ticker = t  # z.B. "FRA:R5A"
        yahoo_symbol = ""

        if t.startswith("FRA:"):
            yahoo_symbol = t.replace("FRA:", "") + ".F"
        elif t.startswith("ETR:"):
            yahoo_symbol = t.replace("ETR:", "") + ".DE"
        elif t.startswith("CVE:"):
            yahoo_symbol = t.replace("CVE:", "") + ".V"
        elif t.startswith("NASDAQ:"):
            yahoo_symbol = t.replace("NASDAQ:", "")
        else:
            # Fallback für unbekannte Präfixe, sollte aber nicht vorkommen
            yahoo_symbol = t

        converted_tickers.append((original_ticker, yahoo_symbol))
    return converted_tickers


def _get_ticker_info_and_history(yahoo_ticker_symbol, history_period):
    """Fetches ticker info and historical data."""
    ticker = yf.Ticker(yahoo_ticker_symbol)
    info = ticker.info
    hist_short = ticker.history(period=history_period)
    hist_max = ticker.history(period="max")
    return ticker, info, hist_short, hist_max


def _calculate_sma_value(hist_short, sma_period):
    """Calculates the Simple Moving Average."""
    if hist_short.empty or len(hist_short) < sma_period:
        return pd.NA
    sma_series = hist_short["Close"].rolling(window=sma_period).mean()
    return sma_series.iloc[-1]


def _calculate_pe_ratio(info, curr_p):
    """Calculates the Price-to-Earnings ratio."""
    pe_v = info.get("trailingPE") or info.get("forwardPE")
    if pe_v is None or pe_v == "None":
        eps = info.get("trailingEps")
        pe_v = curr_p / eps if (eps and eps != 0) else "N/A"
    return pe_v


def _determine_ath_atl_status(hist_max, curr_p, ath_atl_threshold_percent):
    """Determines if the current price is near All-Time High/Low."""
    ath_atl_status = "N/A"
    if not hist_max.empty:
        all_time_high = hist_max["High"].max()
        all_time_low = hist_max["Low"].min()

        threshold_high = all_time_high * (1 - ath_atl_threshold_percent / 100)
        threshold_low = all_time_low * (1 + ath_atl_threshold_percent / 100)

        if curr_p >= threshold_high:
            ath_atl_status = "Nahe ATH"
        elif curr_p <= threshold_low:
            ath_atl_status = "Nahe ATL"
        else:
            ath_atl_status = "Normal"
    return ath_atl_status


def _determine_valuation_status(pe_v, info, pe_cheap_threshold, pe_expensive_threshold, peg_max_threshold):
    """Determines the valuation status based on P/E and PEG ratios."""
    valuation_status = "N/A"
    if isinstance(pe_v, (int, float)):
        if pe_v <= pe_cheap_threshold:
            valuation_status = "Günstig"
        elif pe_v >= pe_expensive_threshold:
            valuation_status = "Teuer"
        else:
            valuation_status = "Fair"

        earnings_growth = info.get('earningsGrowth')  # Annual EPS growth
        if earnings_growth is not None and earnings_growth > 0:
            peg_v = pe_v / (earnings_growth * 100)  # Convert growth to percentage
            if peg_v <= peg_max_threshold:
                if valuation_status == "Günstig":
                    valuation_status = "Sehr Günstig (PEG)"
                elif valuation_status == "Fair":
                    valuation_status = "Fair (PEG)"
            else:
                if valuation_status == "Günstig":
                    valuation_status = "Günstig (Hoher PEG)"
                elif valuation_status == "Fair":
                    valuation_status = "Fair (Hoher PEG)"
                elif valuation_status == "Teuer":
                    valuation_status = "Sehr Teuer (Hoher PEG)"
    return valuation_status


def _get_optional_metrics(info, include_dividend_yield, include_market_cap):
    """Fetches and formats optional metrics like dividend yield and market cap."""
    dividend_yield = "N/A"
    if include_dividend_yield:
        div_yield = info.get("dividendYield")
        if div_yield is not None:
            dividend_yield = round(div_yield * 100, 2)  # In Prozent

    market_cap = "N/A"
    if include_market_cap:
        mkt_cap = info.get("marketCap")
        if mkt_cap is not None:
            market_cap = format_large_number(mkt_cap)
    return dividend_yield, market_cap


def _determine_trend_status(curr_p, sma_v, pe_v, kgv_max_threshold):
    """Determines the trend status."""
    is_bullish = False
    if not pd.isna(sma_v):
        is_bullish = curr_p > sma_v

    trend = (
        "BULLISH"
        if is_bullish
        and (
            isinstance(pe_v, (int, float))
            and pe_v < kgv_max_threshold
            or pe_v == "N/A"
        )
        else "HALTEN"
    )
    return trend


def get_financial_metrics(ticker_tuple):
    """
    Holt Daten von Yahoo Finance und berechnet Kennzahlen für ein gegebenes Ticker-Tupel.
    Erwartet ein Tupel (original_ticker, yahoo_ticker_symbol).
    Implementiert einen Retry-Mechanismus.
    """
    original_ticker, yahoo_ticker_symbol = ticker_tuple
    company_name = "N/A"  # Initialisiere Firmenname für Fehlerfälle

    for attempt in range(RETRIES):
        try:
            ticker, info, hist_short, hist_max = _get_ticker_info_and_history(yahoo_ticker_symbol, HISTORY_PERIOD)
            company_name = info.get("longName", "N/A")

            if hist_short.empty or len(hist_short) < SMA_PERIOD:
                logging.warning(
                    f"[{original_ticker}] Keine/unzureichende Daten für "
                    f"{yahoo_ticker_symbol} (Versuch {attempt + 1}/{RETRIES})."
                )
                return {
                    "Original_Ticker": original_ticker,
                    "Yahoo_Symbol": yahoo_ticker_symbol,
                    "Firmenname": company_name,
                    "Preis": pd.NA,
                    "SMA": pd.NA,
                    "KGV": pd.NA,
                    "Trend": "N/A",
                    "ATH/ATL": "N/A",
                    "Valuation": "N/A",
                    "Status": "Keine/unzureichende Daten (Delisted? Falsches Symbol?)",
                }

            curr_p = hist_short["Close"].iloc[-1]
            sma_v = _calculate_sma_value(hist_short, SMA_PERIOD)
            pe_v = _calculate_pe_ratio(info, curr_p)
            ath_atl_status = _determine_ath_atl_status(hist_max, curr_p, ATH_ATL_THRESHOLD_PERCENT)
            valuation_status = _determine_valuation_status(pe_v, info, PE_CHEAP_THRESHOLD, PE_EXPENSIVE_THRESHOLD, PEG_MAX_THRESHOLD)
            dividend_yield, market_cap = _get_optional_metrics(info, INCLUDE_DIVIDEND_YIELD, INCLUDE_MARKET_CAP)
            trend = _determine_trend_status(curr_p, sma_v, pe_v, KGV_MAX_THRESHOLD)

            result = {
                "Original_Ticker": original_ticker,
                "Yahoo_Symbol": yahoo_ticker_symbol,
                "Firmenname": company_name,
                "Preis": round(curr_p, 2),
                "SMA": round(sma_v, 2) if not pd.isna(sma_v) else "N/A",
                "KGV": round(pe_v, 2) if isinstance(pe_v, (int, float)) else "N/A",
                "Trend": trend,
                "ATH/ATL": ath_atl_status,
                "Valuation": valuation_status,
                "Status": "OK",
            }
            if INCLUDE_DIVIDEND_YIELD:
                result["Dividendenrendite (%)"] = dividend_yield
            if INCLUDE_MARKET_CAP:
                result["Marktkapitalisierung"] = market_cap

            return result

        except Exception as e:
            logging.error(
                f"[{original_ticker}] Fehler bei Abruf von {yahoo_ticker_symbol} (Versuch {attempt + 1}/{RETRIES}): {e}"
            )
            if attempt < RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                return {
                    "Original_Ticker": original_ticker,
                    "Yahoo_Symbol": yahoo_ticker_symbol,
                    "Firmenname": company_name,
                    "Preis": pd.NA,
                    "SMA": pd.NA,
                    "KGV": pd.NA,
                    "Trend": "N/A",
                    "ATH/ATL": "N/A",
                    "Valuation": "N/A",
                    "Status": f"Fehler nach {RETRIES} Versuchen: {str(e)}",
                }
    return {
        "Original_Ticker": original_ticker,
        "Yahoo_Symbol": yahoo_ticker_symbol,
        "Firmenname": "N/A",
        "Preis": pd.NA,
        "SMA": pd.NA,
        "KGV": pd.NA,
        "Trend": "N/A",
        "ATH/ATL": "N/A",
        "Valuation": "N/A",
        "Status": "Unbekannter Fehler",
    }


def analyze_tickers(ticker_tuples_list):
    """
    Hauptfunktion zur Analyse einer Liste von Ticker-Symbol-Tupeln.
    Gibt ein Pandas DataFrame mit den Ergebnissen zurück.
    """
    if not ticker_tuples_list:
        logging.warning("Keine Ticker-Symbole zur Analyse bereitgestellt.")
        return pd.DataFrame()

    logging.info(
        f"Analyse von {len(ticker_tuples_list)} Tickers gestartet (parallelisiert)."
    )

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for res in tqdm(
            executor.map(get_financial_metrics, ticker_tuples_list),
            total=len(ticker_tuples_list),
            desc="Verarbeite Ticker",
        ):
            results.append(res)

    df = pd.DataFrame(results)

    # Sortierung anwenden, falls konfiguriert und Spalte existiert
    if SORT_BY_COLUMN in df.columns:
        df[SORT_BY_COLUMN] = pd.to_numeric(df[SORT_BY_COLUMN], errors="coerce")
        df = df.sort_values(
            by=SORT_BY_COLUMN, ascending=SORT_ASCENDING, na_position="last"
        )
        logging.info(
            f"Ergebnisse sortiert nach '{SORT_BY_COLUMN}' (aufsteigend: {SORT_ASCENDING})."
        )
    else:
        logging.warning(
            f"Sortierspalte '{SORT_BY_COLUMN}' nicht gefunden. Keine Sortierung angewendet."
        )

    return df