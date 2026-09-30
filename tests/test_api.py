"""Unit tests for FastAPI endpoints in api.py without requiring httpx."""

import pytest
from unittest.mock import patch
import pandas as pd
from api import read_root, search_tickers, analyze_financial_data


@pytest.mark.anyio
async def test_read_root():
    res = await read_root()
    assert "message" in res
    assert "Financial Analyzer API" in res["message"]


@pytest.mark.anyio
async def test_search_tickers():
    with patch(
        "api.search_company",
        return_value=[
            {
                "symbol": "SAP",
                "name": "SAP SE",
                "exchange": "ETR",
                "type": "EQUITY",
            }
        ],
    ):
        res = await search_tickers("SAP")
        assert len(res) == 1
        assert res[0]["symbol"] == "SAP"


@pytest.mark.anyio
async def test_analyze_financial_data_custom():
    mock_df = pd.DataFrame(
        [
            {
                "Original Ticker": "AAPL",
                "Yahoo Symbol": "AAPL",
                "Price": 150.0,
                "Status": "OK",
            }
        ]
    )

    with patch("api.analyze_tickers", return_value=mock_df):
        res = await analyze_financial_data(tickers="NASDAQ:AAPL")
        assert len(res) == 1
        assert res[0]["Original Ticker"] == "AAPL"


@pytest.mark.anyio
async def test_analyze_financial_data_no_valid_tickers():
    res = await analyze_financial_data(tickers="NO_VALID_TICKERS_HERE")
    assert res == []


@pytest.mark.anyio
async def test_analyze_financial_data_default():
    mock_df = pd.DataFrame([{"Company": "Mocked", "Status": "OK"}])
    with patch("api.analyze_tickers", return_value=mock_df):
        res = await analyze_financial_data(tickers=None)
        assert len(res) == 1
        assert res[0]["Company"] == "Mocked"
