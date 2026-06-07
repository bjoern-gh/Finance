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
    _calculate_sma_value,
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
    sma = _calculate_sma_value(hist_short, sma_period)
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
            "Nahe ATH",
        ),  # Near ATH
        ({"High": [100, 110, 120], "Low": [80, 85, 90]}, 82, 5, "Nahe ATL"),  # Near ATL
        ({"High": [100, 110, 120], "Low": [80, 85, 90]}, 100, 5, "Normal"),  # Normal
        (
            {"High": [100, 110, 120], "Low": [80, 85, 90]},
            120,
            0,
            "Nahe ATH",
        ),  # Exactly ATH, 0% threshold
        (
            {"High": [100, 110, 120], "Low": [80, 85, 90]},
            80,
            0,
            "Nahe ATL",
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
        (10.0, 0.20, "Sehr Günstig (PEG)"),  # Cheap PE, good PEG
        (10.0, 0.05, "Günstig (Hoher PEG)"),  # Cheap PE, high PEG
        (20.0, 0.20, "Fair (PEG)"),  # Fair PE, good PEG
        (20.0, 0.05, "Fair (Hoher PEG)"),  # Fair PE, high PEG
        (35.0, 0.40, "Teuer"),  # Expensive PE, good PEG (still expensive)
        (35.0, 0.05, "Sehr Teuer (Hoher PEG)"),  # Expensive PE, high PEG
        (10.0, None, "Günstig"),  # Cheap PE, no growth
        (20.0, None, "Fair"),  # Fair PE, no growth
        (35.0, None, "Teuer"),  # Expensive PE, no growth
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
    div_yield, mkt_cap = _get_optional_metrics(
        info, include_dividend_yield, include_market_cap
    )
    if pd.isna(expected_div_yield):
        assert pd.isna(div_yield)
    else:
        assert div_yield == expected_div_yield

    if pd.isna(expected_mkt_cap):
        assert pd.isna(mkt_cap)
    else:
        assert mkt_cap == expected_mkt_cap


@pytest.mark.parametrize(
    "curr_p, sma_v, pe_v, kgv_max_threshold, expected_trend",
    [
        (105, 100, 20, 25, "BULLISH"),  # Price > SMA, PE < KGV_MAX
        (95, 100, 20, 25, "HALTEN"),  # Price < SMA
        (105, 100, 30, 25, "HALTEN"),  # Price > SMA, PE > KGV_MAX
        (
            105,
            100,
            pd.NA,
            25,
            "BULLISH",
        ),  # Price > SMA, PE is pd.NA, changed from "N/A"
        (105, pd.NA, 20, 25, "HALTEN"),  # SMA is N/A
        (pd.NA, 100, 20, 25, "HALTEN"),  # Current price is N/A
    ],
)
def test_determine_trend_status(curr_p, sma_v, pe_v, kgv_max_threshold, expected_trend):
    trend = _determine_trend_status(curr_p, sma_v, pe_v, kgv_max_threshold)
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
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
        (
            "General",
            "kgv_max_threshold",
        ): 30,  # Adjusted for test_get_financial_metrics_valuation
    }.get((section, option))
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
    assert (
        result["ATH/ATL"] == "Normal"
    )  # Current price 105, ATH 120, ATL 80. 5% threshold: 120*0.95 = 114, 80*1.05 = 84. 105 is between 84 and 114.
    assert (
        result["Valuation"] == "Fair (Hoher PEG)"
    )  # PE 25 (Fair), PEG 25/(10*100) = 2.5 (High PEG) -> should be Fair (Hoher PEG)
    assert result["Status"] == "OK"
    assert result["Dividendenrendite (%)"] == 0.50
    assert result["Marktkapitalisierung"] == "2.00T"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_no_data(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
        ("General", "kgv_max_threshold"): 25,
    }.get((section, option))
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
        pd.DataFrame(),  # Second call for hist_max (empty)
    ]

    ticker_tuple = ("NASDAQ:NODATA", "NODATA")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:NODATA"
    assert result["Yahoo_Symbol"] == "NODATA"
    assert result["Firmenname"] == "No Data Co."
    assert pd.isna(result["Preis"])
    assert pd.isna(result["SMA"])
    assert pd.isna(result["KGV"])
    assert result["Trend"] == "N/A"
    assert result["ATH/ATL"] == "N/A"
    assert result["Valuation"] == "N/A"
    assert "Keine/unzureichende Daten" in result["Status"]


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_api_error(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
        ("General", "kgv_max_threshold"): 25,
    }.get((section, option))
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

    ticker_tuple = ("NASDAQ:ERROR", "ERROR")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:ERROR"
    assert result["Yahoo_Symbol"] == "ERROR"
    assert result["Firmenname"] == "Error Co."  # Company name should be available
    assert pd.isna(result["Preis"])
    assert pd.isna(result["SMA"])
    assert pd.isna(result["KGV"])
    assert result["Trend"] == "N/A"
    assert result["ATH/ATL"] == "N/A"
    assert result["Valuation"] == "N/A"
    assert "Fehler nach 1 Versuchen: API Limit Exceeded" in result["Status"]


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_kgv_threshold(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "kgv_max_threshold"): 20,  # Set a lower threshold
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
    }.get((section, option))
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

    ticker_tuple = ("NASDAQ:HIGHKGV", "HIGHKGV")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:HIGHKGV"
    assert result["Yahoo_Symbol"] == "HIGHKGV"
    assert result["Firmenname"] == "High KGV Co."
    assert result["Preis"] == 105.00
    assert result["SMA"] == 104.50
    assert result["KGV"] == 25.00
    assert result["Trend"] == "HALTEN"  # KGV is above threshold, so not BULLISH
    assert result["ATH/ATL"] == "Normal"
    assert result["Valuation"] == "Fair (Hoher PEG)"  # PE 25 (Fair), PEG 2.5 (High PEG)
    assert result["Status"] == "OK"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_no_pe_but_eps(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "kgv_max_threshold"): 30,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
    }.get((section, option))
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

    ticker_tuple = ("NASDAQ:EPSONLY", "EPSONLY")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:EPSONLY"
    assert result["Yahoo_Symbol"] == "EPSONLY"
    assert result["Firmenname"] == "EPS Only Co."
    assert result["Preis"] == 100.00
    assert result["SMA"] == 102.00  # (104+100)/2
    assert result["KGV"] == 25.00
    assert result["Trend"] == "HALTEN"  # Price 100 is not > SMA 102
    assert result["ATH/ATL"] == "Normal"
    assert result["Valuation"] == "Fair (Hoher PEG)"  # PE 25 (Fair), PEG 2.5 (High PEG)
    assert result["Status"] == "OK"


@patch("financial_analyzer.yf.Ticker")
@patch("financial_analyzer.config")
@patch(
    "financial_analyzer.logging"
)  # Mock logging to prevent console output during tests
def test_get_financial_metrics_no_pe_no_eps(mock_logging, mock_config, MockTicker):
    mock_config.get.return_value = "1y"
    mock_config.getint.side_effect = lambda section, option: {
        ("General", "sma_period"): 2,
        ("General", "kgv_max_threshold"): 30,
        ("General", "retries"): 1,
        ("General", "retry_delay_seconds"): 0,
        ("General", "ath_atl_threshold_percent"): 5,
    }.get((section, option))
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

    ticker_tuple = ("NASDAQ:NOPEEPS", "NOPEEPS")
    result = get_financial_metrics(ticker_tuple)

    assert result["Original_Ticker"] == "NASDAQ:NOPEEPS"
    assert result["Yahoo_Symbol"] == "NOPEEPS"
    assert result["Firmenname"] == "No PE/EPS Co."
    assert result["Preis"] == 105.00
    assert result["SMA"] == 104.50  # Corrected from pd.isna(result["SMA"])
    assert pd.isna(result["KGV"])
    assert (
        result["Trend"] == "BULLISH"
    )  # Price > SMA, and KGV is N/A (which is treated as not exceeding threshold)
    assert result["ATH/ATL"] == "Normal"
    assert result["Valuation"] == "N/A"  # No PE or EPS, so no valuation
    assert result["Status"] == "OK"


@pytest.mark.parametrize(
    "pe_value, earnings_growth, expected_valuation",
    [
        (10.0, 0.20, "Sehr Günstig (PEG)"),  # Cheap PE, good PEG
        (10.0, 0.05, "Günstig (Hoher PEG)"),  # Cheap PE, high PEG
        (20.0, 0.20, "Fair (PEG)"),  # Fair PE, good PEG
        (20.0, 0.05, "Fair (Hoher PEG)"),  # Fair PE, high PEG
        (35.0, 0.40, "Teuer"),  # Expensive PE, good PEG (still expensive)
        (35.0, 0.05, "Sehr Teuer (Hoher PEG)"),  # Expensive PE, high PEG
        (10.0, None, "Günstig"),  # Cheap PE, no growth
        (20.0, None, "Fair"),  # Fair PE, no growth
        (35.0, None, "Teuer"),  # Expensive PE, no growth
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
