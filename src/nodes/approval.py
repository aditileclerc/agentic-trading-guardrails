"""
human_approval: pauses the graph and waits for an explicit approve/reject
decision before a trade can proceed to execution.

Uses LangGraph's `interrupt()`, which is the framework's native
human-in-the-loop primitive: calling it suspends the graph, persists state
via the checkpointer, and returns control to whatever is driving the graph
(main.py). The graph resumes exactly where it left off once `Command(resume=...)`
is sent back in — this is NOT a manual input() call inside the node, which
would block the whole process and wouldn't survive a restart.

This node is only ever reached if the pre_approval guardrail check passed
(see graph.py's conditional edges), so by the time a human sees a
proposal here, it has already cleared the size cap, allow-list, and daily
limit checks.
"""

from langgraph.types import interrupt

from src.state import TradingState


def approval_node(state: TradingState) -> TradingState:
    proposal = state["proposal"]

    decision = interrupt(
        {
            "type": "trade_approval_request",
            "proposal": proposal,
            "prompt": (
                f"Proposed: {proposal['side'].upper()} ${proposal['amount_usd']} "
                f"of {proposal['ticker']}\nReasoning: {proposal['reasoning']}\n"
                f"Approve this trade? (yes/no)"
            ),
        }
    )

    # `decision` is whatever value was passed into Command(resume=...) by
    # the caller (see main.py) — expected to be "approved" or "rejected".
    updates: TradingState = {"human_decision": decision}
    if decision != "approved":
        updates["outcome"] = "rejected_by_human"
    return updates
