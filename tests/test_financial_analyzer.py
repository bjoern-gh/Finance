import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys
import os

# Add the project root to the Python path to allow importing financial_analyzer
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from financial_analyzer import (
    parse_and_convert_tickers,
    format_large_number,
    get_financial_metrics,
)


# Test cases for parse_and_convert_tickers
@pytest.mark.parametrize(
    "input_string, expected_output",
    [
        ("FRA:R5A", [("FRA:R5A", "R5A.F")]),
        ("ETR:DAI", [("ETR:DAI", "DAI.DE")]),
        ("CVE:ACB", [("CVE:ACB", "ACB.V")]),
        ("NASDAQ:AAPL", [("NASDAQ:AAPL", "AAPL")]),
        ("FRA:R5AETR:DAI", [("FRA:R5A", "R5A.F"), ("ETR:DAI", "DAI.DE")]),
        (
            "Some text FRA:R5A more text NASDAQ:GOOGL end",
            [("FRA:R5A", "R5A.F"), ("NASDAQ:GOOGL", "GOOGL")],
        ),
        ("", []),
        ("No matching tickers here", []),
        ("FRA:R5A, ETR:DAI", [("FRA:R5A", "R5A.F")]),  # Only takes contiguous matches
    ],
)
def test_parse_and_convert_tickers(input_string, expected_output):
    assert parse_and_convert_tickers(input_string) == expected_output


# Test cases for format_large_number
@pytest.mark.parametrize(
    "input_number, expected_output",
    [
        (1234, "1.23K"),
        (1234567, "1.23M"),
        (1234567890, "1.23B"),
        (123, "123.00"),  # No suffix for numbers less than 1000
        (0, "0.00"),
        (-1234, "-1.23K"),
        (1234567890123, "1.23T"),
        (123.45, "123.45"),
        ("not a number", "not a number"),  # Should return as is
        (None, None),  # Should return as is
    ],
)
def test_format_large_number(input_number, expected_output):
    assert format_large_number(input_number) == expected_output


# Test cases for get_financial_metrics
# We need to mock yfinance.Ticker and its methods
@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")  # Mock the config to control settings
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_success(mock_logging, mock_config, MockTicker):
    # Setup mock config values
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
    }.get((section, option))
    mock_config.getboolean.side_effect = lambda section, option: {
        ("Metrics", "include_dividend_yield"): True,
        ("Metrics", "include_market_cap"): True,
    }.get((section, option))

    # Setup yfinance.Ticker mock
    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    # Mock ticker.info
    mock_ticker_instance.info = {
        "longName": "Apple Inc.",
        "trailingPE": 25.0,
        "forwardPE": 24.0,
        "dividendYield": 0.005,  # 0.5%
        "marketCap": 2_000_000_000_000,  # 2 Trillion
    }

    # Mock ticker.history
    mock_hist_df = pd.DataFrame(
        {"Close": [100, 101, 102, 103, 104, 105]},  # Enough data for SMA_PERIOD=2
        index=pd.to_datetime(
            [
                "2023-01-01",
                "2023-01-02",
                "2023-01-03",
                "2023-01-04",
                "2023-01-05",
                "2023-01-06",
            ]
        ),
    )
    mock_ticker_instance.history.return_value = mock_hist_df

    ticker_tuple = ("NASDAQ:AAPL", "AAPL")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:AAPL"
    assert result["Yahoo_Symbol"] == "AAPL"
    assert result["Firmenname"] == "Apple Inc."
    assert result["Preis"] == 105.00
    assert result["SMA"] == 104.50  # (104+105)/2
    assert result["KGV"] == 25.00
    assert (
        result["Trend"] == "BULLISH"
    )  # 105 > 104.50 and KGV < KGV_MAX_THRESHOLD (default 25, but mocked to 25)
    assert result["Status"] == "OK"
    assert result["Dividendenrendite (%)"] == 0.50
    assert result["Marktkapitalisierung"] == "2.00T"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch("financial_analyzer.logging")
def test_get_financial_metrics_no_data(mock_logging, mock_config, MockTicker):
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
    }.get((section, option))
    mock_config.getboolean.return_value = False  # Don't include optional metrics

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {"longName": "No Data Co."}
    mock_ticker_instance.history.return_value = pd.DataFrame()  # Empty history

    ticker_tuple = ("NASDAQ:NODATA", "NODATA")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:NODATA"
    assert result["Yahoo_Symbol"] == "NODATA"
    assert result["Firmenname"] == "No Data Co."
    assert pd.isna(result["Preis"])
    assert pd.isna(result["SMA"])
    assert pd.isna(result["KGV"])
    assert result["Trend"] == "N/A"
    assert "Keine/unzureichende Daten" in result["Status"]


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch("financial_analyzer.logging")
def test_get_financial_metrics_api_error(mock_logging, mock_config, MockTicker):
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
    }.get((section, option))
    mock_config.getboolean.return_value = False

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {"longName": "Error Co."}
    mock_ticker_instance.history.side_effect = Exception(
        "API Limit Exceeded"
    )  # Simulate API error

    ticker_tuple = ("NASDAQ:ERROR", "ERROR")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:ERROR"
    assert result["Yahoo_Symbol"] == "ERROR"
    assert result["Firmenname"] == "Error Co."
    assert pd.isna(result["Preis"])
    assert pd.isna(result["SMA"])
    assert pd.isna(result["KGV"])
    assert result["Trend"] == "N/A"
    assert "Fehler nach 1 Versuchen: API Limit Exceeded" in result["Status"]


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch("financial_analyzer.logging")
def test_get_financial_metrics_kgv_threshold(mock_logging, mock_config, MockTicker):
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "kgv_max_threshold"): 20,  # Set a lower threshold
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
    }.get((section, option))
    mock_config.getboolean.return_value = False

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {
        "longName": "High KGV Co.",
        "trailingPE": 25.0,  # KGV above threshold
    }

    mock_hist_df = pd.DataFrame(
        {"Close": [100, 101, 102, 103, 104, 105]},
        index=pd.to_datetime(
            [
                "2023-01-01",
                "2023-01-02",
                "2023-01-03",
                "2023-01-04",
                "2023-01-05",
                "2023-01-06",
            ]
        ),
    )
    mock_ticker_instance.history.return_value = mock_hist_df

    ticker_tuple = ("NASDAQ:HIGHKGV", "HIGHKGV")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:HIGHKGV"
    assert result["Yahoo_Symbol"] == "HIGHKGV"
    assert result["Firmenname"] == "High KGV Co."
    assert result["Preis"] == 105.00
    assert result["SMA"] == 104.50
    assert result["KGV"] == 25.00
    assert result["Trend"] == "HALTEN"  # KGV is above threshold, so not BULLISH
    assert result["Status"] == "OK"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch("financial_analyzer.logging")
def test_get_financial_metrics_no_pe_but_eps(mock_logging, mock_config, MockTicker):
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "kgv_max_threshold"): 30,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
    }.get((section, option))
    mock_config.getboolean.return_value = False

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {
        "longName": "EPS Only Co.",
        "trailingEps": 4.0,  # PE is missing, but EPS is present
        "trailingPE": None,
        "forwardPE": None,
    }

    mock_hist_df = pd.DataFrame(
        {"Close": [100, 101, 102, 103, 104, 100]},  # Price 100, EPS 4 -> KGV 25
        index=pd.to_datetime(
            [
                "2023-01-01",
                "2023-01-02",
                "2023-01-03",
                "2023-01-04",
                "2023-01-05",
                "2023-01-06",
            ]
        ),
    )
    mock_ticker_instance.history.return_value = mock_hist_df

    ticker_tuple = ("NASDAQ:EPSONLY", "EPSONLY")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:EPSONLY"
    assert result["Yahoo_Symbol"] == "EPSONLY"
    assert result["Firmenname"] == "EPS Only Co."
    assert result["Preis"] == 100.00
    assert result["SMA"] == 102.00  # (104+100)/2
    assert result["KGV"] == 25.00
    assert result["Trend"] == "HALTEN"  # Price 100 is not > SMA 102
    assert result["Status"] == "OK"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch("financial_analyzer.logging")
def test_get_financial_metrics_no_pe_no_eps(mock_logging, mock_config, MockTicker):
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "kgv_max_threshold"): 30,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
    }.get((section, option))
    mock_config.getboolean.return_value = False

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {
        "longName": "No PE/EPS Co.",
        "trailingEps": None,
        "trailingPE": None,
        "forwardPE": None,
    }

    mock_hist_df = pd.DataFrame(
        {"Close": [100, 101, 102, 103, 104, 105]},
        index=pd.to_datetime(
            [
                "2023-01-01",
                "2023-01-02",
                "2023-01-03",
                "2023-01-04",
                "2023-01-05",
                "2023-01-06",
            ]
        ),
    )
    mock_ticker_instance.history.return_value = mock_hist_df

    ticker_tuple = ("NASDAQ:NOPEEPS", "NOPEEPS")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:NOPEEPS"
    assert result["Yahoo_Symbol"] == "NOPEEPS"
    assert result["Firmenname"] == "No PE/EPS Co."
    assert result["Preis"] == 105.00
    assert result["SMA"] == 104.50
    assert result["KGV"] == "N/A"
    assert (
        result["Trend"] == "BULLISH"
    )  # Price > SMA, and KGV is N/A (which is treated as not exceeding threshold)
    assert result["Status"] == "OK"
