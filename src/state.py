"""
Shared state schema passed between every node in the graph.

Kept as a single flat TypedDict (rather than nested agent-specific state)
so every node — including the guardrail and logging nodes, which are plain
Python and not LLM calls — can read and write to the same object without
translation.
"""

from typing import TypedDict, Literal, Optional


class TradeProposal(TypedDict):
    ticker: str
    side: Literal["buy", "sell"]
    amount_usd: float
    reasoning: str


class GuardrailResult(TypedDict):
    passed: bool
    reasons: list[str]  # human-readable reasons for any failure(s)


class TradingState(TypedDict, total=False):
    # --- research_agent output ---
    portfolio: dict          # raw portfolio/positions/balances from MCP
    analysis: str            # research_agent's natural-language analysis

    # --- execution_agent output ---
    proposal: Optional[TradeProposal]

    # --- guardrail_check output (written twice: pre- and post-approval) ---
    guardrail_result: Optional[GuardrailResult]
    guardrail_stage: Literal["pre_approval", "pre_execution"]

    # --- human_approval output ---
    human_decision: Optional[Literal["approved", "rejected"]]

    # --- order_execution output ---
    execution_result: Optional[dict]

    # --- terminal status used to route to decision_log with the right outcome ---
    outcome: Literal[
        "rejected_by_guardrail",
        "rejected_by_human",
        "executed",
        "execution_failed",
    ]
