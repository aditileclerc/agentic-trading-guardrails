"""
order_execution: calls the Robinhood MCP's order-placement tool.

This is the ONLY node in the entire graph permitted to reach the
write/order tool, and the graph is wired (see graph.py) so this node is
only reachable after BOTH the pre_approval and pre_execution guardrail
checks have passed AND a human has explicitly approved the proposal.
There is no path through the graph that reaches this node otherwise.
"""

from src.state import TradingState


async def order_execution_node(state: TradingState, order_tool) -> TradingState:
    """
    `order_tool` is the specific MCP order-placement tool, located by name
    from the tool list loaded in graph.py and passed in explicitly here —
    deliberately NOT the full tool list, so this node has no way to
    accidentally reach any other tool.
    """
    proposal = state["proposal"]

    try:
        result = await order_tool.ainvoke(
            {
                "ticker": proposal["ticker"],
                "side": proposal["side"],
                "amount_usd": proposal["amount_usd"],
            }
        )
        return {"execution_result": {"status": "success", "detail": result},
                "outcome": "executed"}
    except Exception as e:  # noqa: BLE001 - surface any failure into the log
        return {"execution_result": {"status": "error", "detail": str(e)},
                "outcome": "execution_failed"}
