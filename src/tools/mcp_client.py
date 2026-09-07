"""
Thin wrapper around langchain-mcp-adapters for connecting to the Robinhood
Trading MCP server (or the local mock server with the same tool shapes).

Kept in one place so both research_agent (read tools) and order_execution
(write tool) go through the same connection setup, and so swapping the
target (real Robinhood MCP <-> local mock) is a one-line env change, not a
code change.
"""

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config import MCP_SERVER_URL


def get_mcp_client() -> MultiServerMCPClient:
    """
    Returns a client configured to talk to a single MCP server: either the
    real Robinhood Trading MCP or the local mock, depending on
    MCP_SERVER_URL in the environment.
    """
    return MultiServerMCPClient(
        {
            "robinhood-trading": {
                "url": MCP_SERVER_URL,
                "transport": "streamable_http",
            }
        }
    )


async def load_mcp_tools() -> list:
    """
    Fetches the full tool list exposed by the MCP server (read tools like
    positions/balances/order-history, plus the order-placement tool) as
    LangChain-compatible tools.

    Read and write tools are NOT separated at this layer on purpose — the
    guardrail layer is what controls whether the order-placement tool is
    ever actually reachable, not which tools get loaded. See
    src/nodes/guardrails.py and src/nodes/approval.py.
    """
    client = get_mcp_client()
    return await client.get_tools()
