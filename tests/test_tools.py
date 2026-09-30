"""Unit tests for tools and search_company modules."""

from unittest.mock import patch, MagicMock
import portfolio_manager as pm
import tools
from financial_analyzer import search_company


def test_search_company_empty_query():
    assert search_company("") == []
    assert search_company("   ") == []
    assert search_company("a") == []  # under 2 chars


def test_search_company_mocked_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "quotes": [
            {
                "symbol": "AAPL",
                "longname": "Apple Inc.",
                "exchDisp": "NASDAQ",
                "quoteType": "EQUITY",
            },
            {
                "symbol": "AAPL.DE",
                "longname": "Apple Inc. (XETRA)",
                "exchDisp": "XETRA",
                "quoteType": "EQUITY",
            },
            {
                "symbol": "IGNORED",
                "quoteType": "CRYPTOCURRENCY",  # Should be filtered out
            },
        ]
    }

    with patch("requests.get", return_value=mock_response):
        results = search_company("Apple")
        assert len(results) == 2
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["name"] == "Apple Inc."
        assert results[1]["symbol"] == "AAPL.DE"


def test_tools_list_portfolios(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "PORTFOLIOS_DIR", tmp_path)
    # Empty
    assert "No portfolios found" in tools.list_portfolios()

    # With portfolios
    pm.save_portfolio("Tech", [])
    pm.save_portfolio("Mining", [])
    result = tools.list_portfolios()
    assert "Mining" in result
    assert "Tech" in result


def test_tools_get_portfolio_info(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "PORTFOLIOS_DIR", tmp_path)
    pm.save_portfolio(
        "Divs",
        [
            {
                "original": "JNJ",
                "yahoo": "JNJ",
                "display_name": "Johnson & Johnson",
            }
        ],
    )

    info = tools.get_portfolio_info("Divs")
    assert "Johnson & Johnson" in info
    assert "JNJ" in info

    empty_info = tools.get_portfolio_info("NonExistent")
    assert "is empty" in empty_info


def test_tools_add_and_remove_ticker(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "PORTFOLIOS_DIR", tmp_path)
    pm.save_portfolio("PortfolioA", [])

    add_res = tools.add_ticker_to_portfolio(
        "PortfolioA", "AAPL", "AAPL", "Apple Inc."
    )
    assert "Successfully added" in add_res

    # Try duplicate
    add_dup = tools.add_ticker_to_portfolio(
        "PortfolioA", "AAPL", "AAPL", "Apple Inc."
    )
    assert "Failed to add" in add_dup

    # Remove
    rem_res = tools.remove_ticker_from_portfolio("PortfolioA", "AAPL")
    assert "Successfully removed" in rem_res


def test_tools_get_market_search():
    with patch(
        "tools.search_company",
        return_value=[
            {
                "symbol": "NVDA",
                "name": "NVIDIA Corporation",
                "exchange": "NASDAQ",
            }
        ],
    ):
        res = tools.get_market_search("Nvidia")
        assert "NVIDIA Corporation" in res
        assert "NVDA" in res
