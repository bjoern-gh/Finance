"""Unit tests for agent.py and FinancialAgent."""

from unittest.mock import MagicMock
from agent import FinancialAgent


def test_agent_no_model_client():
    agent = FinancialAgent(model_client=None)
    response = agent.run("Show my portfolios")
    assert "No model client provided" in response


def test_agent_text_response():
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.tool_calls = None
    mock_msg.content = "Here is financial advice."
    mock_client.generate_response.return_value = mock_msg

    agent = FinancialAgent(model_client=mock_client)
    res = agent.run("What is Apple's price?")
    assert res == "Here is financial advice."


def test_agent_tool_call_execution():
    mock_client = MagicMock()
    mock_msg = MagicMock()

    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "list_portfolios"
    mock_tool_call.function.arguments = "{}"
    mock_msg.tool_calls = [mock_tool_call]
    mock_client.generate_response.return_value = mock_msg

    agent = FinancialAgent(model_client=mock_client)
    res = agent.run("List my portfolios")
    assert "Available portfolios" in res or "No portfolios found" in res
