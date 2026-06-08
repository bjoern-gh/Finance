from fastapi import FastAPI, Query
from typing import List, Optional
import logging
import configparser

from financial_analyzer import analyze_tickers, parse_and_convert_tickers

app = FastAPI(
    title="Financial Analyzer API",
    description="API for analyzing financial tickers using Yahoo Finance data.",
    version="2.0.0",
)

logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read("config.ini")
DEFAULT_RAW_DATA = config.get("General", "raw_data")


@app.get("/")
async def read_root():
    return {
        "message": "Welcome to the Financial Analyzer API! Visit /docs for API documentation."
    }


@app.get("/analyze", response_model=List[dict])
async def analyze_financial_data(
    tickers: Optional[str] = Query(
        None,
        description=(
            "Comma-separated ticker symbols with optional exchange prefix "
            "(e.g. 'FRA:RWE,ETR:SAP,NASDAQ:AAPL,NYSE:IBM'). "
            "If not provided, uses the default list from config.ini."
        ),
    ),
):
    """
    Analyze a list of financial tickers and return computed metrics.
    """
    raw_string = tickers if tickers else DEFAULT_RAW_DATA
    logger.info(f"Analyzing tickers from string: {raw_string[:80]}...")

    # Parse raw string into (original, yahoo) tuples before passing to analyzer
    ticker_tuples = parse_and_convert_tickers(raw_string)

    if not ticker_tuples:
        logger.warning("No valid ticker symbols found in input.")
        return []

    df_results = analyze_tickers(ticker_tuples)
    return df_results.to_dict(orient="records")
