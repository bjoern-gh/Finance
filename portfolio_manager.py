"""
Portfolio Manager — stores portfolios as JSON files in a local portfolios/ directory.

Each portfolio file: portfolios/<name>.json
Schema: {"name": str, "tickers": [{"original": str, "yahoo": str, "display_name": str}]}
"""

import json
import os
from pathlib import Path

PORTFOLIOS_DIR = Path("portfolios")


def _ensure_dir():
    PORTFOLIOS_DIR.mkdir(exist_ok=True)


def list_portfolios() -> list[str]:
    """Return sorted list of portfolio names (without .json extension)."""
    _ensure_dir()
    return sorted(f.stem for f in PORTFOLIOS_DIR.glob("*.json"))


def load_portfolio(name: str) -> dict:
    """Load portfolio by name. Returns empty portfolio dict if not found."""
    _ensure_dir()
    path = PORTFOLIOS_DIR / f"{name}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"name": name, "tickers": []}


def save_portfolio(name: str, tickers: list[dict]) -> None:
    """
    Save portfolio. tickers is a list of dicts:
      {"original": str, "yahoo": str, "display_name": str}
    """
    _ensure_dir()
    path = PORTFOLIOS_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"name": name, "tickers": tickers}, f, indent=2, ensure_ascii=False)


def delete_portfolio(name: str) -> bool:
    """Delete portfolio file. Returns True if deleted, False if not found."""
    path = PORTFOLIOS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def rename_portfolio(old_name: str, new_name: str) -> bool:
    """Rename a portfolio. Returns True on success."""
    if not old_name or not new_name or old_name == new_name:
        return False
    old_path = PORTFOLIOS_DIR / f"{old_name}.json"
    new_path = PORTFOLIOS_DIR / f"{new_name}.json"
    if not old_path.exists():
        return False
    data = load_portfolio(old_name)
    data["name"] = new_name
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    old_path.unlink()
    return True


def add_ticker(name: str, original: str, yahoo: str, display_name: str) -> bool:
    """
    Add a ticker to a portfolio. Returns False if already present.
    """
    portfolio = load_portfolio(name)
    existing_yahoo = {t["yahoo"] for t in portfolio["tickers"]}
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
        t for t in portfolio["tickers"] if t["yahoo"] != yahoo_symbol
    ]
    save_portfolio(name, portfolio["tickers"])
