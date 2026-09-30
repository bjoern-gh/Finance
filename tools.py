import portfolio_manager as pm
from financial_analyzer import (
    analyze_tickers,
    get_financial_metrics,
    search_company,
)

# This module provides tools for the Financial Analysis Agent.
# Each function is designed to be called by an LLM to perform specific actions.


def get_portfolio_info(portfolio_name: str) -> str:
    """
    Returns the current portfolio name and a list of tickers.
    Use this to understand what stocks are currently being tracked.
    """
    data = pm.load_portfolio(portfolio_name)
    tickers = data.get("tickers", [])
    if not tickers:
        return f"Portfolio '{portfolio_name}' is empty."
    lines = [f"Portfolio: {portfolio_name} ({len(tickers)} stocks):"]
    for t in tickers:
        name = t.get("display_name") or t.get("original")
        lines.append(f"- {name} ({t.get('yahoo')})")
    return "\n".join(lines)


def list_portfolios() -> str:
    """
    Returns a list of all available portfolio names.
    Use this to see which portfolios exist.
    """
    portfolios = pm.list_portfolios()
    if not portfolios:
        return "No portfolios found."
    return "Available portfolios: " + ", ".join(portfolios)


def get_analysis_for_ticker(ticker_tuple: tuple[str, str]) -> str:
    """
    Fetches financial metrics for a specific ticker (original_ticker, yahoo_symbol).
    Returns a summary of the metrics.
    """
    result = get_financial_metrics(ticker_tuple)
    if result.get("Status") != "OK":
        return f"Error analyzing {ticker_tuple[0]}: {result.get('Status')}"

    # Convert to a readable string for the agent
    summary = f"Metrics for {result.get('Company')} ({result.get('Yahoo Symbol')}):\n"
    summary += f"- Price: {result.get('Price')} {result.get('Currency', '')}\n"
    summary += f"- Trend: {result.get('Trend')}\n"
    summary += f"- Valuation: {result.get('Valuation')}\n"
    summary += f"- RSI: {result.get('RSI')}\n"
    summary += f"- SMA200: {result.get('SMA200')}\n"
    summary += f"- Business Model: {result.get('Business Model')}\n"
    return summary


def add_ticker_to_portfolio(
    portfolio_name: str, original_ticker: str, yahoo_symbol: str, display_name: str
) -> str:
    """
    Adds a new ticker to a specific portfolio.
    """
    success = pm.add_ticker(portfolio_name, original_ticker, yahoo_symbol, display_name)
    if success:
        return (
            f"Successfully added {display_name} ({yahoo_symbol}) to {portfolio_name}."
        )
    return f"Failed to add {display_name} to {portfolio_name}."


def remove_ticker_from_portfolio(portfolio_name: str, yahoo_symbol: str) -> str:
    """
    Removes a ticker from a portfolio.
    """
    pm.remove_ticker(portfolio_name, yahoo_symbol)
    return f"Successfully removed {yahoo_symbol} from {portfolio_name}."


def get_market_search(query: str) -> str:
    """
    Searches Yahoo Finance for companies matching a query.
    Returns a list of symbols and names.
    """
    if not query:
        return "Please provide a search query."

    search_results = search_company(query)
    if not search_results:
        return f"No results found for '{query}'."

    summary = f"Found {len(search_results)} matches for '{query}':\n"
    for r in search_results[:5]:
        summary += f"- {r.get('name')} ({r.get('symbol')}) - {r.get('exchange')}\n"
    return summary.strip()


def run_bulk_analysis(portfolio_name: str) -> str:
    """
    Runs a full analysis on all tickers in the specified portfolio.
    Returns a summary of the results.
    """
    data = pm.load_portfolio(portfolio_name)
    tickers = data.get("tickers", [])
    if not tickers:
        return f"Portfolio '{portfolio_name}' has no tickers to analyze."

    ticker_tuples = [
        (t.get("original", t.get("yahoo")), t.get("yahoo")) for t in tickers
    ]
    df = analyze_tickers(ticker_tuples)
    if df.empty:
        return f"No analysis results returned for '{portfolio_name}'."

    lines = [f"Analysis results for '{portfolio_name}':"]
    for _, row in df.iterrows():
        lines.append(
            f"- {row.get('Company')} ({row.get('Yahoo Symbol')}): Price={row.get('Price')}, "
            f"Trend={row.get('Trend')}, Valuation={row.get('Valuation')}"
        )
    return "\n".join(lines)
