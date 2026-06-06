from fastapi import FastAPI, Query
from typing import List, Optional
import logging
import configparser  # Importiere configparser

# Importiere die Analysefunktion aus unserem Modul
from financial_analyzer import analyze_tickers

app = FastAPI(
    title="Financial Analyzer API",
    description="API for analyzing financial tickers using Yahoo Finance data.",
    version="1.0.0",
)

# Konfiguriere den Logger für die API
logger = logging.getLogger(__name__)

# --- Konfiguration laden (für DEFAULT_RAW_DATA) ---
config = configparser.ConfigParser()
config.read("config.ini")
DEFAULT_RAW_DATA = config.get("General", "raw_data")


@app.get("/")
async def read_root():
    """
    Einfacher Root-Endpunkt zur Überprüfung der API-Verfügbarkeit.
    """
    return {
        "message": "Welcome to the Financial Analyzer API! Visit /docs for API documentation."
    }


@app.get("/analyze", response_model=List[dict])
async def analyze_financial_data(
    tickers: Optional[str] = Query(
        None,
        description="Comma-separated list of ticker symbols to analyze (e.g., 'FRA:RWE,ETR:SAP'). "
        "If not provided, uses the default list from config.ini.",
    )
):
    """
    Analysiert eine Liste von Finanz-Tickern und gibt die berechneten Kennzahlen zurück.
    """
    if tickers:
        raw_data_string = tickers
        logger.info(f"Analyzing provided tickers: {tickers}")
    else:
        raw_data_string = DEFAULT_RAW_DATA
        logger.info("Analyzing default tickers from config.ini.")

    # Rufe die Analysefunktion auf
    df_results = analyze_tickers(raw_data_string)

    # Konvertiere das DataFrame in eine Liste von Dictionaries für die JSON-Antwort
    # NaN-Werte werden standardmäßig zu null in JSON konvertiert
    return df_results.to_dict(orient="records")
