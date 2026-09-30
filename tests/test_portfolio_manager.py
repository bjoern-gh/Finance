"""Unit tests for portfolio_manager module."""

import json
import pytest
import portfolio_manager as pm


@pytest.fixture
def temp_portfolios_dir(tmp_path, monkeypatch):
    """Point PORTFOLIOS_DIR to a temporary directory for clean test isolation."""
    portfolios_dir = tmp_path / "portfolios"
    portfolios_dir.mkdir()
    monkeypatch.setattr(pm, "PORTFOLIOS_DIR", portfolios_dir)
    return portfolios_dir


def test_list_portfolios_empty(temp_portfolios_dir):
    assert pm.list_portfolios() == []


def test_save_and_load_portfolio(temp_portfolios_dir):
    tickers = [
        {"original": "AAPL", "yahoo": "AAPL", "display_name": "Apple Inc."},
        {"original": "MSFT", "yahoo": "MSFT", "display_name": "Microsoft Corp."},
    ]
    pm.save_portfolio("Tech", tickers)

    assert pm.list_portfolios() == ["Tech"]
    assert pm.portfolio_exists("Tech") is True

    loaded = pm.load_portfolio("Tech")
    assert loaded["name"] == "Tech"
    assert loaded["tickers"] == tickers


def test_load_nonexistent_portfolio(temp_portfolios_dir):
    loaded = pm.load_portfolio("NonExistent")
    assert loaded == {"name": "NonExistent", "tickers": []}


def test_load_corrupted_json_portfolio(temp_portfolios_dir):
    corrupt_file = temp_portfolios_dir / "Corrupt.json"
    corrupt_file.write_text("This is not valid json! {", encoding="utf-8")

    loaded = pm.load_portfolio("Corrupt")
    assert loaded == {"name": "Corrupt", "tickers": []}


def test_load_invalid_structure_portfolio(temp_portfolios_dir):
    invalid_file = temp_portfolios_dir / "Invalid.json"
    invalid_file.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

    loaded = pm.load_portfolio("Invalid")
    assert loaded == {"name": "Invalid", "tickers": []}


def test_delete_portfolio(temp_portfolios_dir):
    pm.save_portfolio("ToDelete", [])
    assert pm.portfolio_exists("ToDelete") is True

    deleted = pm.delete_portfolio("ToDelete")
    assert deleted is True
    assert pm.portfolio_exists("ToDelete") is False

    # Deleting again should return False
    assert pm.delete_portfolio("ToDelete") is False


def test_rename_portfolio(temp_portfolios_dir):
    tickers = [{"original": "NVDA", "yahoo": "NVDA", "display_name": "Nvidia"}]
    pm.save_portfolio("OldName", tickers)

    renamed = pm.rename_portfolio("OldName", "NewName")
    assert renamed is True
    assert pm.portfolio_exists("OldName") is False
    assert pm.portfolio_exists("NewName") is True

    loaded = pm.load_portfolio("NewName")
    assert loaded["name"] == "NewName"
    assert loaded["tickers"] == tickers


def test_rename_invalid_arguments(temp_portfolios_dir):
    assert pm.rename_portfolio("", "New") is False
    assert pm.rename_portfolio("Old", "") is False
    assert pm.rename_portfolio("Same", "Same") is False
    assert pm.rename_portfolio("NonExistent", "NewName") is False


def test_add_and_remove_ticker(temp_portfolios_dir):
    pm.save_portfolio("Watchlist", [])

    # Add first ticker
    added = pm.add_ticker("Watchlist", "AAPL", "AAPL", "Apple")
    assert added is True

    # Duplicate should return False
    added_again = pm.add_ticker("Watchlist", "AAPL", "AAPL", "Apple")
    assert added_again is False

    # Add second ticker
    pm.add_ticker("Watchlist", "TSLA", "TSLA", "Tesla")
    loaded = pm.load_portfolio("Watchlist")
    assert len(loaded["tickers"]) == 2

    # Remove first ticker
    pm.remove_ticker("Watchlist", "AAPL")
    loaded_after = pm.load_portfolio("Watchlist")
    assert len(loaded_after["tickers"]) == 1
    assert loaded_after["tickers"][0]["yahoo"] == "TSLA"
