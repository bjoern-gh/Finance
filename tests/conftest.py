"""Pytest configuration and fixtures."""

import os

os.environ["ARROW_DEFAULT_MEMORY_POOL"] = "system"
import sys
import pytest
from unittest.mock import patch

# Ensure the project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment: change to project root so config.ini is found."""
    original_cwd = os.getcwd()
    os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    yield
    os.chdir(original_cwd)


@pytest.fixture
def mock_config():
    """Mock configparser for consistent test configuration."""
    with patch("financial_analyzer.config") as mock:
        mock.get.return_value = "1y"
        mock.getint.side_effect = lambda section, option, fallback=None: {
            ("General", "sma_period"): 200,
            ("General", "sma_short_period"): 50,
            ("General", "rsi_period"): 14,
            ("General", "max_workers"): 10,
            ("General", "retries"): 3,
            ("General", "retry_delay_seconds"): 5,
            ("General", "ath_atl_threshold_percent"): 5,
            ("General", "kgv_max_threshold"): 25,
            ("General", "sort_ascending"): 0,  # getboolean returns 0/1
        }.get((section, option), fallback)
        mock.getboolean.side_effect = lambda section, option: {
            ("Metrics", "include_dividend_yield"): True,
            ("Metrics", "include_market_cap"): True,
        }.get((section, option), False)
        mock.getfloat.side_effect = lambda section, option: {
            ("General", "pe_cheap_threshold"): 15.0,
            ("General", "pe_expensive_threshold"): 30.0,
            ("General", "peg_max_threshold"): 1.0,
        }.get((section, option))
        yield mock
