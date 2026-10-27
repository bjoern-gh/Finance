import json
import logging
from typing import Any

# Assuming 'tools' contains the definitions for function_call objects.
# These are likely protobuf/dataclasses that map to the API schema.
from tools import (
    get_analysis_for_ticker,
    get_market_search,
    get_portfolio_info,
    list_portfolios,
    remove_ticker_from_portfolio,
    run_bulk_analysis,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OpenAIClient:
    """Simple client for OpenAI-compatible APIs."""

    def __init__(self, api_key: str, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url
        import openai

        self.client = openai.OpenAI(api_key=self.api_key, base_url=base_url)

    def generate_response(
        self, prompt: str, tools: list[dict[str, Any]]
    ) -> Any:
        """
        Generates a response from OpenAI by executing the chat completion.

        Args:
            prompt: The user's natural language prompt.
            tools: The full internal definitions of available functions (self.tools).

        Returns:
            The LLM's message response object.
        """
        # CRITICAL FIX: Map the verbose internal tool definitions (tools)
        # into the minimal, API-compliant structure required by the OpenAI client.
        tools_def: Any = [
            {"type": t["type"], "function": t["function"]} for t in tools
        ]

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    # Including the full tools definition in system prompt for context.
                    "content": f"You are a financial assistant. Available Tools: {json.dumps(tools, default=str)}",
                    "name": "system",
                },
                {"role": "user", "content": prompt},
            ],
            # CORRECTED: Pass the minimal API-compliant structure here.
            tools=tools_def,
            tool_choice="auto",
        )
        return response.choices[0].message


class FinancialAgent:
    def __init__(self, model_client=None):
        """
        Initialize the agent with a model client.
        """
        self.model_client = model_client
        # self.tools holds the full, detailed definitions used internally by our application.
        self.tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "list_portfolios",
                    "description": "Returns a list of all available portfolio names.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
                "function_call": list_portfolios,
            },
            {
                "type": "function",
                "function": {
                    "name": "get_portfolio_info",
                    "description": "Returns the list of stocks currently in a portfolio.",
                    "parameters": {
                        "type": "object",
                        "properties": {"portfolio_name": {"type": "string"}},
                        "required": ["portfolio_name"],
                    },
                },
                "function_call": get_portfolio_info,
            },
            {
                "type": "function",
                "function": {
                    "name": "get_analysis_for_ticker",
                    "description": "Fetches financial metrics for a specific ticker (original_ticker, yahoo_symbol).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker_tuple": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tuple [original, yahoo]",
                            }
                        },
                        "required": ["ticker_tuple"],
                    },
                },
                "function_call": get_analysis_for_ticker,
            },
            {
                "type": "function",
                "function": {
                    "name": "remove_ticker_from_portfolio",
                    "description": "Removes a ticker from a portfolio.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "portfolio_name": {"type": "string"},
                            "yahoo_symbol": {"type": "string"},
                        },
                        "required": ["portfolio_name", "yahoo_symbol"],
                    },
                },
                "function_call": remove_ticker_from_portfolio,
            },
            {
                "type": "function",
                "function": {
                    "name": "get_market_search",
                    "description": "Searches Yahoo Finance for companies matching a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
                "function_call": get_market_search,
            },
            {
                "type": "function",
                "function": {
                    "name": "run_bulk_analysis",
                    "description": "Runs a full analysis on all tickers in a portfolio.",
                    "parameters": {
                        "type": "object",
                        "properties": {"portfolio_name": {"type": "string"}},
                        "required": ["portfolio_name"],
                    },
                },
                "function_call": run_bulk_analysis,
            },
        ]

    def run(self, user_input: str, current_portfolio: str | None = None) -> str:
        if not self.model_client:
            return "Error: No model client provided. Please configure an API key in the settings."

        # Pass the current user input and tools to the model client for processing
        response = self.model_client.generate_response(user_input, self.tools)

        if hasattr(response, "tool_calls") and response.tool_calls:
            results = []
            for tool_call in response.tool_calls:
                fn_name = tool_call.function.name
                # Safely parse arguments passed by the LLM
                fn_args = json.loads(tool_call.function.arguments)

                # Find the matching tool definition to execute the correct function
                tool_def = next(
                    (t for t in self.tools if t["function"]["name"] == fn_name),
                    None,
                )
                if not tool_def:
                    results.append(f"Tool {fn_name} not found.")
                    continue

                # Execute the function call using its bound reference
                fn = tool_def["function_call"]
                logger.info(f"Calling tool: {fn_name} with {fn_args}")
                try:
                    result = fn(**fn_args)
                    results.append(str(result))
                except Exception as e:
                    logger.exception(f"Error calling {fn_name}")
                    results.append(f"Error calling {fn_name}: {e}")

            return "\n\n".join(results)

        # Return the simple text content response if no tool calls were requested
        return getattr(response, "content", str(response))
