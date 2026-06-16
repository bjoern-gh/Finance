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
    _calculate_sma,
    _calculate_pe_ratio,
    _determine_ath_atl_status,
    _determine_valuation_status,
    _get_optional_metrics,
    _determine_trend_status,
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
        (
            "FRA:R5A, ETR:DAI",
            [("FRA:R5A", "R5A.F"), ("ETR:DAI", "DAI.DE")],
        ),  # Supports comma-separated list
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


# --- Tests for helper functions ---


@pytest.mark.parametrize(
    "close_prices, sma_period, expected_sma",
    [
        ([10, 11, 12, 13, 14], 3, 13.0),  # Basic SMA
        ([10, 11, 12, 13, 14], 5, 12.0),  # Full SMA
        ([10, 11], 3, pd.NA),  # Not enough data
        ([], 3, pd.NA),  # Empty data
        ([10, 11, 12], 3, 11.0),  # Exact match
    ],
)
def test_calculate_sma_value(close_prices, sma_period, expected_sma):
    hist_short = pd.DataFrame({"Close": close_prices})
    sma = _calculate_sma(hist_short, sma_period)
    if pd.isna(expected_sma):
        assert pd.isna(sma)
    else:
        assert sma == expected_sma


@pytest.mark.parametrize(
    "info, curr_p, expected_pe",
    [
        ({"trailingPE": 20.0}, 100, 20.0),
        ({"forwardPE": 18.0}, 100, 18.0),
        (
            {"trailingPE": None, "forwardPE": None, "trailingEps": 5.0},
            100,
            20.0,
        ),  # PE from EPS
        (
            {"trailingPE": None, "forwardPE": None, "trailingEps": 0},
            100,
            pd.NA,
        ),  # EPS is zero, changed to pd.NA
        (
            {"trailingPE": None, "forwardPE": None, "trailingEps": None},
            100,
            pd.NA,
        ),  # No PE, no EPS, changed to pd.NA
        ({}, 100, pd.NA),  # Empty info, changed to pd.NA
    ],
)
def test_calculate_pe_ratio(info, curr_p, expected_pe):
    pe = _calculate_pe_ratio(info, curr_p)
    if pd.isna(expected_pe):
        assert pd.isna(pe)
    else:
        assert pe == expected_pe


@pytest.mark.parametrize(
    "hist_max_data, curr_p, ath_atl_threshold_percent, expected_status",
    [
        (
            {"High": [100, 110, 120], "Low": [80, 85, 90]},
            118,
            5,
            "Near ATH",
        ),  # Near ATH
        ({"High": [100, 110, 120], "Low": [80, 85, 90]}, 82, 5, "Near ATL"),  # Near ATL
        ({"High": [100, 110, 120], "Low": [80, 85, 90]}, 100, 5, "Normal"),  # Normal
        (
            {"High": [100, 110, 120], "Low": [80, 85, 90]},
            120,
            0,
            "Near ATH",
        ),  # Exactly ATH, 0% threshold
        (
            {"High": [100, 110, 120], "Low": [80, 85, 90]},
            80,
            0,
            "Near ATL",
        ),  # Exactly ATL, 0% threshold
        ({"High": [], "Low": []}, 100, 5, "N/A"),  # Empty hist_max
    ],
)
def test_determine_ath_atl_status(
    hist_max_data, curr_p, ath_atl_threshold_percent, expected_status
):
    hist_max = pd.DataFrame(hist_max_data)
    status = _determine_ath_atl_status(hist_max, curr_p, ath_atl_threshold_percent)
    assert status == expected_status


@pytest.mark.parametrize(
    "pe_value, earnings_growth, expected_valuation",
    [
        (10.0, 0.20, "Very Cheap (PEG)"),  # Cheap PE, good PEG
        (10.0, 0.05, "Cheap (High PEG)"),  # Cheap PE, high PEG
        (20.0, 0.20, "Fair (Good PEG)"),  # Fair PE, good PEG
        (20.0, 0.05, "Fair (High PEG)"),  # Fair PE, high PEG
        (35.0, 0.40, "Expensive"),  # Expensive PE, good PEG (still expensive)
        (35.0, 0.05, "Very Expensive (PEG)"),  # Expensive PE, high PEG
        (10.0, None, "Cheap"),  # Cheap PE, no growth
        (20.0, None, "Fair"),  # Fair PE, no growth
        (35.0, None, "Expensive"),  # Expensive PE, no growth
        (pd.NA, 0.10, "N/A"),  # No PE, but growth, changed to pd.NA
        (pd.NA, None, "N/A"),  # No PE, no growth, changed to pd.NA
    ],
)
def test_determine_valuation_status(pe_value, earnings_growth, expected_valuation):
    info = {"earningsGrowth": earnings_growth}
    pe_cheap_threshold = 15.0
    pe_expensive_threshold = 30.0
    peg_max_threshold = 1.0

    valuation = _determine_valuation_status(
        pe_value, info, pe_cheap_threshold, pe_expensive_threshold, peg_max_threshold
    )
    assert valuation == expected_valuation


@pytest.mark.parametrize(
    "info, include_dividend_yield, include_market_cap, expected_div_yield, expected_mkt_cap",
    [
        (
            {"dividendYield": 0.02, "marketCap": 1_000_000_000},
            True,
            True,
            2.00,
            "1.00B",
        ),
        (
            {"dividendYield": None, "marketCap": 500_000},
            True,
            True,
            pd.NA,
            "500.00K",
        ),  # Changed to pd.NA
        ({"dividendYield": 0.01}, True, False, 1.00, pd.NA),  # Changed to pd.NA
        (
            {"marketCap": 2_000_000_000_000},
            False,
            True,
            pd.NA,
            "2.00T",
        ),  # Changed to pd.NA
        ({}, False, False, pd.NA, pd.NA),  # Changed to pd.NA
    ],
)
def test_get_optional_metrics(
    info,
    include_dividend_yield,
    include_market_cap,
    expected_div_yield,
    expected_mkt_cap,
):
    # Mock the global config variables for these tests
    with patch(
        "financial_analyzer.INCLUDE_DIVIDEND_YIELD", include_dividend_yield
    ), patch("financial_analyzer.INCLUDE_MARKET_CAP", include_market_cap):
        result = _get_optional_metrics(info)
        div_yield = result.get("Dividend Yield (%)")
        mkt_cap = result.get("Market Cap")

        if pd.isna(expected_div_yield):
            assert pd.isna(div_yield)
        else:
            assert div_yield == expected_div_yield

        if pd.isna(expected_mkt_cap):
            assert pd.isna(mkt_cap)
        else:
            assert mkt_cap == expected_mkt_cap


@pytest.mark.parametrize(
    "curr_p, sma200, sma50, rsi, pe_v, kgv_max_threshold, expected_trend",
    [
        (
            105,
            100,
            102,
            50,
            20,
            25,
            "STRONG BUY",
        ),  # Price > SMA50 > SMA200, RSI ok, PE ok
        (
            105,
            100,
            pd.NA,
            50,
            20,
            25,
            "BULLISH",
        ),  # Price > SMA200, SMA50 NA, RSI ok, PE ok
        (105, 100, 102, 80, 20, 25, "OVERBOUGHT"),  # Price > SMA200, RSI overbought
        (105, 100, 102, 50, 30, 25, "HOLD"),  # Price > SMA200, PE too high
        (95, 100, 98, 20, 20, 25, "OVERSOLD"),  # Price < SMA200, RSI oversold
        (95, 100, 98, 50, 20, 25, "BEARISH"),  # Price < SMA200
        (pd.NA, 100, 102, 50, 20, 25, "HOLD"),  # Current price is N/A
        (105, pd.NA, 102, 50, 20, 25, "HOLD"),  # SMA200 is N/A
    ],
)
def test_determine_trend_status(
    curr_p, sma200, sma50, rsi, pe_v, kgv_max_threshold, expected_trend
):
    trend = _determine_trend_status(curr_p, sma200, sma50, rsi, pe_v, kgv_max_threshold)
    assert trend == expected_trend


# --- Original tests for get_financial_metrics (integration tests) ---


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")  # Mock the config to control settings
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_success(mock_logging, mock_config, MockTicker):
    # Setup mock config values
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option, fallback=None: {
        ("General", "sma_period"): 2,
        ("General", "sma_short_period"): 2,  # Added for SMA50
        ("General", "rsi_period"): 14,  # Added for RSI
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
        (
            "General",
            "kgv_max_threshold",
        ): 30,  # Adjusted for test_get_financial_metrics_valuation
    }.get((section, option), fallback)
    mock_config.getboolean.side_effect = lambda section, option: {
        ("Metrics", "include_dividend_yield"): True,
        ("Metrics", "include_market_cap"): True,
    }.get((section, option))
    mock_config.getfloat.side_effect = lambda section, option: {
        ("General", "pe_cheap_threshold"): 15.0,
        ("General", "pe_expensive_threshold"): 30.0,
        ("General", "peg_max_threshold"): 1.0,
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
        "earningsGrowth": 0.10,  # 10% growth for PEG
        "currency": "USD",
        "fiftyTwoWeekHigh": 120,
        "fiftyTwoWeekLow": 80,
        "debtToEquity": 50,
        "revenueGrowth": 0.15,
        "profitMargins": 0.20,
        "beta": 1.2,
        "sector": "Technology",
    }

    # Mock ticker.history
    mock_hist_df_short = pd.DataFrame(
        {
            "Close": [100, 101, 102, 103, 104, 105],
            "High": [100, 101, 102, 103, 104, 105],
            "Low": [90, 91, 92, 93, 94, 95],
        },  # Enough data for SMA_PERIOD=2
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
    mock_hist_df_max = pd.DataFrame(
        {"High": [100, 110, 120, 105], "Low": [80, 85, 90, 95]},  # For hist_max
        index=pd.to_datetime(["2022-01-01", "2022-01-02", "2022-01-03", "2022-01-04"]),
    )
    mock_ticker_instance.history.side_effect = [
        mock_hist_df_short,  # First call for HISTORY_PERIOD
        mock_hist_df_max,  # Second call for period="max"
    ]

    # Mock _get_eur_rate to return a fixed value for testing
    with patch("financial_analyzer._get_eur_rate", return_value=0.9):  # 1 USD = 0.9 EUR
        ticker_tuple = ("NASDAQ:AAPL", "AAPL")
        result = get_financial_metrics(ticker_tuple)

        assert result["Original Ticker"] == "NASDAQ:AAPL"
        assert result["Yahoo Symbol"] == "AAPL"
        assert result["Company"] == "Apple Inc."
        assert result["Price"] == 105.00
        assert result["Price (EUR)"] == 94.50  # 105 * 0.9
        assert result["SMA200"] == 104.50  # (104+105)/2
        assert result["SMA50"] == 104.50  # (104+105)/2
        assert result["RSI"] == 100.0  # Mocked data leads to this
        assert result["P/E (KGV)"] == 25.00
        assert (
            result["Trend"] == "STRONG BUY"
        )  # Price > SMA50 > SMA200, RSI ok, PE ok (25 < 30)
        assert (
            result["ATH/ATL"] == "Normal"
        )  # Current price 105, ATH 120, ATL 80. 5% threshold: 120*0.95 = 114, 80*1.05 = 84. 105 is between 84 and 114.
        assert (
            result["Valuation"] == "Fair (Good PEG)"
        )  # PE 25 (Fair), PEG 25/(10*100) = 2.5 (High PEG) -> should be Fair (Hoher PEG)
        assert result["Status"] == "OK"
        assert result["Dividend Yield (%)"] == 0.50
        assert result["Market Cap"] == "2.00T"
        assert result["52W High (%)"] == -12.5
        assert result["52W Low (%)"] == 31.2
        assert result["D/E Ratio"] == 0.5
        assert result["Revenue Growth (%)"] == 15.0
        assert result["Profit Margin (%)"] == 20.0
        assert result["Beta"] == 1.2
        assert result["Sector"] == "Technology"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_no_data(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option, fallback=None: {
        ("General", "sma_period"): 2,
        ("General", "sma_short_period"): 2,
        ("General", "rsi_period"): 14,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
        ("General", "kgv_max_threshold"): 25,
    }.get((section, option), fallback)
    mock_config.getboolean.return_value = False  # Don't include optional metrics
    mock_config.getfloat.side_effect = lambda section, option: {
        ("General", "pe_cheap_threshold"): 15.0,
        ("General", "pe_expensive_threshold"): 30.0,
        ("General", "peg_max_threshold"): 1.0,
    }.get((section, option))

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {"longName": "No Data Co."}
    mock_ticker_instance.history.side_effect = [
        pd.DataFrame(),  # First call for hist_short (empty)
        pd.DataFrame(),  # Second call for period="max" (empty)
    ]

    with patch("financial_analyzer._get_eur_rate", return_value=1.0):
        ticker_tuple = ("NASDAQ:NODATA", "NODATA")
        result = get_financial_metrics(ticker_tuple)

        assert result["Original Ticker"] == "NASDAQ:NODATA"
        assert result["Yahoo Symbol"] == "NODATA"
        assert result["Company"] == "No Data Co."
        assert pd.isna(result["Price"])
        assert pd.isna(result["SMA200"])
        assert pd.isna(result["SMA50"])
        assert pd.isna(result["RSI"])
        assert pd.isna(result["P/E (KGV)"])
        assert result["Trend"] == "HOLD"  # Default for insufficient data
        assert result["ATH/ATL"] == "N/A"
        assert result["Valuation"] == "N/A"
        assert "Insufficient data (delisted or wrong symbol?)" in result["Status"]


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_api_error(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option, fallback=None: {
        ("General", "sma_period"): 2,
        ("General", "sma_short_period"): 2,
        ("General", "rsi_period"): 14,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
        ("General", "kgv_max_threshold"): 25,
    }.get((section, option), fallback)
    mock_config.getboolean.return_value = False
    mock_config.getfloat.side_effect = lambda section, option: {
        ("General", "pe_cheap_threshold"): 15.0,
        ("General", "pe_expensive_threshold"): 30.0,
        ("General", "peg_max_threshold"): 1.0,
    }.get((section, option))

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    # Mock ticker.info to succeed, but history to fail
    mock_ticker_instance.info = {"longName": "Error Co."}
    mock_ticker_instance.history.side_effect = Exception(
        "API Limit Exceeded"
    )  # Simulate API error on history fetch

    with patch("financial_analyzer._get_eur_rate", return_value=1.0):
        ticker_tuple = ("NASDAQ:ERROR", "ERROR")
        result = get_financial_metrics(ticker_tuple)

        assert result["Original Ticker"] == "NASDAQ:ERROR"
        assert result["Yahoo Symbol"] == "ERROR"
        assert result["Company"] == "Error Co."  # Company name should be available
        assert pd.isna(result["Price"])
        assert pd.isna(result["SMA200"])
        assert pd.isna(result["SMA50"])
        assert pd.isna(result["RSI"])
        assert pd.isna(result["P/E (KGV)"])
        assert result["Trend"] == "N/A"
        assert result["ATH/ATL"] == "N/A"
        assert result["Valuation"] == "N/A"
        assert "Failed after 1 attempts: API Limit Exceeded" in result["Status"]


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_kgv_threshold(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option, fallback=None: {
        ("General", "sma_period"): 2,
        ("General", "sma_short_period"): 2,
        ("General", "rsi_period"): 14,
        ("General", "kgv_max_threshold"): 20,  # Set a lower threshold
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
    }.get((section, option), fallback)
    mock_config.getboolean.return_value = False
    mock_config.getfloat.side_effect = lambda section, option: {
        ("General", "pe_cheap_threshold"): 15.0,
        ("General", "pe_expensive_threshold"): 30.0,
        ("General", "peg_max_threshold"): 1.0,
    }.get((section, option))

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {
        "longName": "High KGV Co.",
        "trailingPE": 25.0,  # KGV above threshold
        "earningsGrowth": 0.10,
        "currency": "USD",
        "fiftyTwoWeekHigh": 120,
        "fiftyTwoWeekLow": 80,
    }

    mock_hist_df_short = pd.DataFrame(
        {
            "Close": [100, 101, 102, 103, 104, 105],
            "High": [100, 110, 120, 105, 105, 105],
            "Low": [80, 85, 90, 95, 95, 95],
        },
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
    mock_hist_df_max = pd.DataFrame(
        {"High": [100, 110, 120, 105], "Low": [80, 85, 90, 95]},  # For hist_max
        index=pd.to_datetime(["2022-01-01", "2022-01-02", "2022-01-03", "2022-01-04"]),
    )
    mock_ticker_instance.history.side_effect = [
        mock_hist_df_short,  # First call for HISTORY_PERIOD
        mock_hist_df_max,  # Second call for period="max"
    ]

    with patch("financial_analyzer._get_eur_rate", return_value=1.0):
        ticker_tuple = ("NASDAQ:HIGHKGV", "HIGHKGV")
        result = get_financial_metrics(ticker_tuple)

        assert result["Original Ticker"] == "NASDAQ:HIGHKGV"
        assert result["Yahoo Symbol"] == "HIGHKGV"
        assert result["Company"] == "High KGV Co."
        assert result["Price"] == 105.00
        assert result["SMA200"] == 104.50
        assert result["SMA50"] == 104.50
        assert result["RSI"] == 100.0
        assert result["P/E (KGV)"] == 25.00
        assert result["Trend"] == "HOLD"  # KGV is above threshold, so not BULLISH
        assert result["ATH/ATL"] == "Normal"
        assert (
            result["Valuation"] == "Fair (High PEG)"
        )  # PE 25 (Fair), PEG 2.5 (High PEG)
        assert result["Status"] == "OK"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_no_pe_but_eps(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option, fallback=None: {
        ("General", "sma_period"): 2,
        ("General", "sma_short_period"): 2,
        ("General", "rsi_period"): 14,
        ("General", "kgv_max_threshold"): 30,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
    }.get((section, option), fallback)
    mock_config.getboolean.return_value = False
    mock_config.getfloat.side_effect = lambda section, option: {
        ("General", "pe_cheap_threshold"): 15.0,
        ("General", "pe_expensive_threshold"): 30.0,
        ("General", "peg_max_threshold"): 1.0,
    }.get((section, option))

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {
        "longName": "EPS Only Co.",
        "trailingEps": 4.0,  # PE is missing, but EPS is present
        "trailingPE": None,
        "forwardPE": None,
        "earningsGrowth": 0.10,
        "currency": "USD",
        "fiftyTwoWeekHigh": 120,
        "fiftyTwoWeekLow": 80,
    }

    mock_hist_df_short = pd.DataFrame(
        {
            "Close": [100, 101, 102, 103, 104, 100],
            "High": [100, 110, 120, 105, 105, 105],
            "Low": [80, 85, 90, 95, 95, 95],
        },  # Price 100, EPS 4 -> KGV 25
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
    mock_hist_df_max = pd.DataFrame(
        {"High": [100, 110, 120, 105], "Low": [80, 85, 90, 95]},  # For hist_max
        index=pd.to_datetime(["2022-01-01", "2022-01-02", "2022-01-03", "2022-01-04"]),
    )
    mock_ticker_instance.history.side_effect = [
        mock_hist_df_short,  # First call for HISTORY_PERIOD
        mock_hist_df_max,  # Second call for period="max"
    ]

    with patch("financial_analyzer._get_eur_rate", return_value=1.0):
        ticker_tuple = ("NASDAQ:EPSONLY", "EPSONLY")
        result = get_financial_metrics(ticker_tuple)

        assert result["Original Ticker"] == "NASDAQ:EPSONLY"
        assert result["Yahoo Symbol"] == "EPSONLY"
        assert result["Company"] == "EPS Only Co."
        assert result["Price"] == 100.00
        assert result["SMA200"] == 102.00  # (104+100)/2
        assert result["SMA50"] == 102.00
        assert result["RSI"] == 100.0
        assert result["P/E (KGV)"] == 25.00
        assert result["Trend"] == "BEARISH"  # Price 100 is not > SMA 102
        assert result["ATH/ATL"] == "Normal"
        assert (
            result["Valuation"] == "Fair (High PEG)"
        )  # PE 25 (Fair), PEG 2.5 (High PEG)
        assert result["Status"] == "OK"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_no_pe_no_eps(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option, fallback=None: {
        ("General", "sma_period"): 2,
        ("General", "sma_short_period"): 2,
        ("General", "rsi_period"): 14,
        ("General", "kgv_max_threshold"): 30,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
    }.get((section, option), fallback)
    mock_config.getboolean.return_value = False
    mock_config.getfloat.side_effect = lambda section, option: {
        ("General", "pe_cheap_threshold"): 15.0,
        ("General", "pe_expensive_threshold"): 30.0,
        ("General", "peg_max_threshold"): 1.0,
    }.get((section, option))

    mock_ticker_instance = MagicMock()
    MockTicker.return_value = mock_ticker_instance

    mock_ticker_instance.info = {
        "longName": "No PE/EPS Co.",
        "trailingEps": None,
        "trailingPE": None,
        "forwardPE": None,
        "earningsGrowth": None,  # No earnings growth
        "currency": "USD",
        "fiftyTwoWeekHigh": 120,
        "fiftyTwoWeekLow": 80,
    }

    mock_hist_df_short = pd.DataFrame(
        {
            "Close": [100, 101, 102, 103, 104, 105],
            "High": [100, 110, 120, 105, 105, 105],
            "Low": [80, 85, 90, 95, 95, 95],
        },
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
    mock_hist_df_max = pd.DataFrame(
        {"High": [100, 110, 120, 105], "Low": [80, 85, 90, 95]},  # For hist_max
        index=pd.to_datetime(["2022-01-01", "2022-01-02", "2022-01-03", "2022-01-04"]),
    )
    mock_ticker_instance.history.side_effect = [
        mock_hist_df_short,  # First call for HISTORY_PERIOD
        mock_hist_df_max,  # Second call for period="max"
    ]

    with patch("financial_analyzer._get_eur_rate", return_value=1.0):
        ticker_tuple = ("NASDAQ:NOPEEPS", "NOPEEPS")
        result = get_financial_metrics(ticker_tuple)

        assert result["Original Ticker"] == "NASDAQ:NOPEEPS"
        assert result["Yahoo Symbol"] == "NOPEEPS"
        assert result["Company"] == "No PE/EPS Co."
        assert result["Price"] == 105.00
        assert result["SMA200"] == 104.50
        assert result["SMA50"] == 104.50
        assert result["RSI"] == 100.0
        assert pd.isna(result["P/E (KGV)"])
        assert (
            result["Trend"] == "BULLISH"
        )  # Price > SMA, and KGV is N/A (which is treated as not exceeding threshold)
        assert result["ATH/ATL"] == "Normal"
        assert result["Valuation"] == "N/A"  # No PE or EPS, so no valuation
        assert result["Status"] == "OK"


@pytest.mark.parametrize(
    "pe_value, earnings_growth, expected_valuation",
    [
        (10.0, 0.20, "Very Cheap (PEG)"),  # Cheap PE, good PEG
        (10.0, 0.05, "Cheap (High PEG)"),  # Cheap PE, high PEG
        (20.0, 0.20, "Fair (Good PEG)"),  # Fair PE, good PEG
        (20.0, 0.05, "Fair (High PEG)"),  # Fair PE, high PEG
        (35.0, 0.40, "Expensive"),  # Expensive PE, good PEG (still expensive)
        (35.0, 0.05, "Very Expensive (PEG)"),  # Expensive PE, high PEG
        (10.0, None, "Cheap"),  # Cheap PE, no growth
        (20.0, None, "Fair"),  # Fair PE, no growth
        (35.0, None, "Expensive"),  # Expensive PE, no growth
        (pd.NA, 0.10, "N/A"),  # No PE, but growth, changed to pd.NA
        (pd.NA, None, "N/A"),  # No PE, no growth, changed to pd.NA
    ],
)
def test_determine_valuation_status_helper(
    pe_value, earnings_growth, expected_valuation
):
    info = {"earningsGrowth": earnings_growth}
    pe_cheap_threshold = 15.0
    pe_expensive_threshold = 30.0
    peg_max_threshold = 1.0

    valuation = _determine_valuation_status(
        pe_value, info, pe_cheap_threshold, pe_expensive_threshold, peg_max_threshold
    )
    assert valuation == expected_valuation
