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

# --- Konfiguration laden ---
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
    pattern = r"(?:FRA:|ETR:|CVE:|NASDAQ:)[A-Z0-9]+?(?=(?:FRA:|ETR:|CVE:|NASDAQ:)|$)"
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


def get_financial_metrics(ticker_tuple):
    """
    Holt Daten von Yahoo Finance und berechnet Kennzahlen für ein gegebenes Ticker-Tupel.
    Erwartet ein Tupel (original_ticker, yahoo_ticker_symbol).
    Implementiert einen Retry-Mechanismus.
    """
    original_ticker, yahoo_ticker_symbol = ticker_tuple
    company_name = "N/A"  # Initialisiere Firmenname für Fehlerfälle
    ath_atl_status = "N/A" # Initialisiere für All-Time High/Low Status

    for attempt in range(RETRIES):
        try:
            ticker = yf.Ticker(yahoo_ticker_symbol)

            # Firmenname abrufen (versuche es früh, falls andere Daten fehlschlagen)
            info = ticker.info
            company_name = info.get("longName", "N/A")

            # Für SMA und aktuellen Preis verwenden wir HISTORY_PERIOD
            hist_short = ticker.history(period=HISTORY_PERIOD)

            if hist_short.empty or len(hist_short) < SMA_PERIOD:
                logging.warning(
                    f"[{original_ticker}] Keine/unzureichende Daten für "
                    f"{yahoo_ticker_symbol} (Versuch {attempt + 1}/{RETRIES})."
                )
                return {
                    "Original_Ticker": original_ticker,
                    "Yahoo_Symbol": yahoo_ticker_symbol,
                    "Firmenname": company_name,
                    "Preis": pd.NA,  # Setze auf NA, da keine Daten
                    "SMA": pd.NA,
                    "KGV": pd.NA,
                    "Trend": "N/A",
                    "ATH/ATL": "N/A", # Neuer Metrik-Platzhalter
                    "Status": "Keine/unzureichende Daten (Delisted? Falsches Symbol?)",
                }

            curr_p = hist_short["Close"].iloc[-1]

            # SMA Berechnung
            if len(hist_short) < SMA_PERIOD:
                sma_v = pd.NA  # Nicht berechenbar
            else:
                sma_series = hist_short["Close"].rolling(window=SMA_PERIOD).mean()
                sma_v = sma_series.iloc[-1]

            # Fundamentaldaten
            pe_v = info.get("trailingPE") or info.get("forwardPE")

            if pe_v is None or pe_v == "None":
                eps = info.get("trailingEps")
                pe_v = curr_p / eps if (eps and eps != 0) else "N/A"

            # --- All-Time High/Low Berechnung ---
            hist_max = ticker.history(period="max")
            if not hist_max.empty:
                all_time_high = hist_max["High"].max()
                all_time_low = hist_max["Low"].min()

                # Schwellenwert für "nahe"
                threshold_high = all_time_high * (1 - ATH_ATL_THRESHOLD_PERCENT / 100)
                threshold_low = all_time_low * (1 + ATH_ATL_THRESHOLD_PERCENT / 100)

                if curr_p >= threshold_high:
                    ath_atl_status = "Nahe ATH"
                elif curr_p <= threshold_low:
                    ath_atl_status = "Nahe ATL"
                else:
                    ath_atl_status = "Normal"
            # --- Ende All-Time High/Low Berechnung ---


            # Zusätzliche Metriken
            dividend_yield = "N/A"
            if INCLUDE_DIVIDEND_YIELD:
                div_yield = info.get("dividendYield")
                if div_yield is not None:
                    dividend_yield = round(div_yield * 100, 2)  # In Prozent

            market_cap = "N/A"
            if INCLUDE_MARKET_CAP:
                mkt_cap = info.get("marketCap")
                if mkt_cap is not None:
                    market_cap = format_large_number(
                        mkt_cap
                    )  # Hier wird die Formatierungsfunktion angewendet

            # Trend-Check
            is_bullish = False
            if not pd.isna(sma_v):
                is_bullish = curr_p > sma_v

            trend = (
                "BULLISH"
                if is_bullish
                and (
                    isinstance(pe_v, (int, float))
                    and pe_v < KGV_MAX_THRESHOLD
                    or pe_v == "N/A"
                )
                else "HALTEN"
            )

            result = {
                "Original_Ticker": original_ticker,
                "Yahoo_Symbol": yahoo_ticker_symbol,
                "Firmenname": company_name,  # Firmenname hinzugefügt
                "Preis": round(curr_p, 2),
                "SMA": round(sma_v, 2) if not pd.isna(sma_v) else "N/A",
                "KGV": round(pe_v, 2) if isinstance(pe_v, (int, float)) else "N/A",
                "Trend": trend,
                "ATH/ATL": ath_atl_status, # Neuer Metrik-Wert
                "Status": "OK",  # Erfolgreiche Abfrage
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
                time.sleep(RETRY_DELAY_SECONDS)  # Warte vor dem nächsten Versuch
            else:
                return {
                    "Original_Ticker": original_ticker,
                    "Yahoo_Symbol": yahoo_ticker_symbol,
                    "Firmenname": company_name,  # Firmenname auch bei Fehler
                    "Preis": pd.NA,  # Setze auf NA, da Fehler
                    "SMA": pd.NA,
                    "KGV": pd.NA,
                    "Trend": "N/A",
                    "ATH/ATL": "N/A", # Neuer Metrik-Platzhalter bei Fehler
                    "Status": f"Fehler nach {RETRIES} Versuchen: {str(e)}",
                }
    return {  # Fallback, sollte nicht erreicht werden
        "Original_Ticker": original_ticker,
        "Yahoo_Symbol": yahoo_ticker_symbol,
        "Firmenname": "N/A",
        "Preis": pd.NA,
        "SMA": pd.NA,
        "KGV": pd.NA,
        "Trend": "N/A",
        "ATH/ATL": "N/A", # Neuer Metrik-Platzhalter bei Fehler
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
        # Konvertiere die Spalte in einen numerischen Typ, um korrekt zu sortieren
        # Fehlerhafte Werte (z.B. "N/A") werden zu NaN und am Ende platziert
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