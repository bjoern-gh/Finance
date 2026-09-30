"""
Portfolio Manager — stores portfolios as JSON files in a local portfolios/ directory.

Each portfolio file: portfolios/<name>.json
Schema: {"name": str, "tickers": [{"original": str, "yahoo": str, "display_name": str}]}
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PORTFOLIOS_DIR = Path("portfolios")


def _ensure_dir() -> None:
    PORTFOLIOS_DIR.mkdir(exist_ok=True)


def _safe_path(name: str) -> Path:
    """Return a safe Path object within PORTFOLIOS_DIR, preventing path traversal."""
    clean_name = Path(name).name.strip()
    if not clean_name:
        raise ValueError("Portfolio name cannot be empty.")
    return PORTFOLIOS_DIR / f"{clean_name}.json"


def list_portfolios() -> list[str]:
    """Return sorted list of portfolio names (without .json extension)."""
    _ensure_dir()
    return sorted(f.stem for f in PORTFOLIOS_DIR.glob("*.json") if not f.name.startswith("."))


def portfolio_exists(name: str) -> bool:
    """Check if a portfolio exists."""
    try:
        return _safe_path(name).exists()
    except ValueError:
        return False


def load_portfolio(name: str) -> dict[str, Any]:
    """
    Load portfolio by name.
    Returns default empty portfolio dict if not found or corrupted.
    """
    _ensure_dir()
    empty_result = {"name": name, "tickers": []}
    try:
        path = _safe_path(name)
    except ValueError:
        return empty_result

    if not path.exists():
        return empty_result

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("tickers"), list):
            data.setdefault("name", name)
            return data
        logger.warning(f"Portfolio '{name}' has invalid structure, resetting to empty.")
        return empty_result
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read portfolio '{name}': {e}. Returning empty portfolio.")
        return empty_result


def save_portfolio(name: str, tickers: list[dict[str, str]]) -> None:
    """
    Atomically save portfolio to disk.
    tickers is a list of dicts: {"original": str, "yahoo": str, "display_name": str}
    """
    _ensure_dir()
    path = _safe_path(name)
    temp_path = PORTFOLIOS_DIR / f".{path.name}.tmp"

    payload = {"name": name, "tickers": tickers}
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
        temp_path.replace(path)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        logger.error(f"Error saving portfolio '{name}': {e}")
        raise


def delete_portfolio(name: str) -> bool:
    """Delete portfolio file. Returns True if deleted, False if not found."""
    try:
        path = _safe_path(name)
        if path.exists():
            path.unlink()
            return True
    except (ValueError, OSError) as e:
        logger.error(f"Error deleting portfolio '{name}': {e}")
    return False


def rename_portfolio(old_name: str, new_name: str) -> bool:
    """Rename a portfolio. Returns True on success."""
    if not old_name or not new_name or old_name.strip() == new_name.strip():
        return False
    try:
        old_path = _safe_path(old_name)
        if not old_path.exists():
            return False
        data = load_portfolio(old_name)
        data["name"] = new_name.strip()
        save_portfolio(new_name.strip(), data.get("tickers", []))
        old_path.unlink()
        return True
    except (ValueError, OSError) as e:
        logger.error(f"Error renaming portfolio '{old_name}' to '{new_name}': {e}")
        return False


def add_ticker(name: str, original: str, yahoo: str, display_name: str) -> bool:
    """
    Add a ticker to a portfolio. Returns False if already present.
    """
    portfolio = load_portfolio(name)
    existing_yahoo = {t.get("yahoo") for t in portfolio.get("tickers", [])}
    if yahoo in existing_yahoo:
        return False
    portfolio["tickers"].append(
        {"original": original, "yahoo": yahoo, "display_name": display_name}
    )
    save_portfolio(name, portfolio["tickers"])
    return True


def remove_ticker(name: str, yahoo_symbol: str) -> None:
    """Remove a ticker from a portfolio by its Yahoo symbol."""
    portfolio = load_portfolio(name)
    portfolio["tickers"] = [
        t for t in portfolio.get("tickers", []) if t.get("yahoo") != yahoo_symbol
    ]
    save_portfolio(name, portfolio["tickers"])
