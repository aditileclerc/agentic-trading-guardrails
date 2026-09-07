"""
Minimal mock MCP server exposing the same tool shapes as Robinhood's
Trading MCP (per their published docs): read tools for
positions/balances/order-history, and one order-placement tool.

Use this while developing or if you don't yet have Robinhood Agentic
Trading access (it's a gated rollout). Swap MCP_SERVER_URL in .env to
point at this instead of the live endpoint — no other code changes
needed, since src/tools/mcp_client.py talks to whatever URL is configured.

Run with: python mock_mcp/server.py
Serves streamable HTTP on http://localhost:8000/mcp
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mock-robinhood-trading")

# In-memory fake portfolio, deliberately small and boring.
_PORTFOLIO = {
    "cash_usd": 143.20,
    "positions": [
        {"ticker": "VOO", "shares": 0.8, "market_value_usd": 380.00},
        {"ticker": "AAPL", "shares": 1.2, "market_value_usd": 258.00},
    ],
}

_ORDER_HISTORY = []


@mcp.tool()
def get_positions() -> dict:
    """Returns current positions and their market values."""
    return {"positions": _PORTFOLIO["positions"]}


@mcp.tool()
def get_balances() -> dict:
    """Returns cash and buying power."""
    return {"cash_usd": _PORTFOLIO["cash_usd"]}


@mcp.tool()
def get_order_history() -> dict:
    """Returns past orders placed through this mock account."""
    return {"orders": _ORDER_HISTORY}


@mcp.tool()
def place_order(ticker: str, side: str, amount_usd: float) -> dict:
    """
    Places a mock order. Does not touch real money or markets — just
    records the order and nudges the fake cash balance, so the graph's
    order_execution node has something real to call and log.
    """
    if side == "buy" and amount_usd > _PORTFOLIO["cash_usd"]:
        return {"status": "rejected", "reason": "insufficient mock cash balance"}

    order = {"ticker": ticker, "side": side, "amount_usd": amount_usd, "status": "filled"}
    _ORDER_HISTORY.append(order)

    if side == "buy":
        _PORTFOLIO["cash_usd"] -= amount_usd
    else:
        _PORTFOLIO["cash_usd"] += amount_usd

    return order


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
