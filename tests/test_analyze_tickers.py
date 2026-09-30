"""Unit tests for analyze_tickers batch processing in financial_analyzer."""

from unittest.mock import patch
import pandas as pd
from financial_analyzer import analyze_tickers


def test_analyze_tickers_empty():
    df = analyze_tickers([])
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_analyze_tickers_sequential():
    sample_tickers = [("AAPL", "AAPL"), ("MSFT", "MSFT")]

    mock_metrics = {
        ("AAPL", "AAPL"): {
            "Original Ticker": "AAPL",
            "Yahoo Symbol": "AAPL",
            "Company": "Apple Inc.",
            "Price": 150.0,
            "P/E (KGV)": 25.0,
            "Trend": "BULLISH",
            "Valuation": "Fair",
            "Status": "OK",
        },
        ("MSFT", "MSFT"): {
            "Original Ticker": "MSFT",
            "Yahoo Symbol": "MSFT",
            "Company": "Microsoft Corp.",
            "Price": 300.0,
            "P/E (KGV)": 30.0,
            "Trend": "STRONG BUY",
            "Valuation": "Fair",
            "Status": "OK",
        },
    }

    with patch(
        "financial_analyzer.get_financial_metrics",
        side_effect=lambda t: mock_metrics[t],
    ), patch("financial_analyzer.config") as mock_cfg:
        mock_cfg.getint.return_value = 1  # 1 worker -> sequential path
        mock_cfg.get.return_value = "P/E (KGV)"
        mock_cfg.getboolean.return_value = True

        df = analyze_tickers(sample_tickers)

        assert len(df) == 2
        assert list(df["Yahoo Symbol"]) == ["AAPL", "MSFT"]
        assert list(df["Price"]) == [150.0, 300.0]


def test_analyze_tickers_parallel():
    sample_tickers = [("AAPL", "AAPL"), ("MSFT", "MSFT"), ("GOOG", "GOOG")]

    mock_metrics = {
        ("AAPL", "AAPL"): {
            "Original Ticker": "AAPL",
            "Yahoo Symbol": "AAPL",
            "Company": "Apple Inc.",
            "Price": 150.0,
            "P/E (KGV)": 28.0,
            "Status": "OK",
        },
        ("MSFT", "MSFT"): {
            "Original Ticker": "MSFT",
            "Yahoo Symbol": "MSFT",
            "Company": "Microsoft Corp.",
            "Price": 300.0,
            "P/E (KGV)": 32.0,
            "Status": "OK",
        },
        ("GOOG", "GOOG"): {
            "Original Ticker": "GOOG",
            "Yahoo Symbol": "GOOG",
            "Company": "Alphabet Inc.",
            "Price": 140.0,
            "P/E (KGV)": 20.0,
            "Status": "OK",
        },
    }

    with patch(
        "financial_analyzer.get_financial_metrics",
        side_effect=lambda t: mock_metrics[t],
    ), patch("financial_analyzer.config") as mock_cfg:
        mock_cfg.getint.return_value = 4  # 4 workers -> parallel ThreadPoolExecutor path
        # Sort ascending by KGV -> GOOG (20.0), AAPL (28.0), MSFT (32.0)
        mock_cfg.get.return_value = "KGV"
        mock_cfg.getboolean.return_value = True

        df = analyze_tickers(sample_tickers)

        assert len(df) == 3
        assert list(df["Yahoo Symbol"]) == ["GOOG", "AAPL", "MSFT"]
        assert list(df["P/E (KGV)"]) == [20.0, 28.0, 32.0]
