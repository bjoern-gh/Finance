import portfolio_manager as pm
from financial_analyzer import get_financial_metrics, parse_and_convert_tickers

# This module provides tools for the Financial Analysis Agent.
# Each function is designed to be called by an LLM to perform specific actions.


def get_portfolio_info() -> str:
    """
    Returns the current portfolio name and a list of tickers.
    Use this to understand what stocks are currently being tracked.
    """
    # Since we want to avoid st dependency in tools, we'll assume state is passed or
    # we'll use a global-ish approach if necessary, but better to pass it.
    # For now, let's just provide a way to list them.
    pass


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
    summary += f"- Price: {result.get('Price')}\n"
    summary += f"- Trend: {result.get('Trend')}\n"
    summary += f"- Valuation: {result.get('Valuation')}\n"
    summary += f"- RSI: {result.get('RSI')}\n"
    summary += f"- SMA200: {result.get('SMA200')}\n"
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
    results = parse_and_convert_tickers(query)
    if not results:
        return "No results found for that query."

    # We need to fetch actual names for these
    # This is a simplified version, in a real agent we might want the full search_company result
    from financial_analyzer import search_company

    search_results = search_company(query)
    if not search_results:
        return "No results found."

    summary = "Found the following matches:\n"
    for r in search_results[:5]:
        summary += f"- {r['name']} ({r['symbol']}) - {r['exchange']}\n"
    return summary


def run_bulk_analysis(portfolio_name: str) -> str:
    """
    Runs a full analysis on all tickers in the specified portfolio.
    Returns a summary of the results.
    """
    # Better to pass the tickers list into this tool.
    pass
