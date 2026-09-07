"""
guardrail_check: plain, deterministic Python. No LLM call happens here on
purpose — whether a trade is within limits should never be a matter of
model judgment.

This function is used TWICE in the graph (see graph.py):
  1. pre_approval  - right after execution_agent drafts a proposal, before
                      a human ever sees it. Filters out obviously-invalid
                      proposals so you're not asked to review garbage.
  2. pre_execution - immediately before the order tool is called, in case
                      anything relevant changed between approval and
                      execution (e.g. another trade today pushed the daily
                      count over the limit).

Because it's pure and side-effect-free (aside from reading the log for the
daily count), it's directly unit-testable — see tests/test_guardrails.py.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from src.config import MAX_ORDER_USD, TICKER_ALLOWLIST, MAX_TRADES_PER_DAY, DECISION_LOG_PATH
from src.state import TradingState, GuardrailResult, TradeProposal


def _trades_in_last_24h() -> int:
    """Counts executed trades in the decision log within the last 24 hours."""
    if not os.path.exists(DECISION_LOG_PATH):
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    with open(DECISION_LOG_PATH, "r") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("outcome") != "executed":
                continue
            ts = datetime.fromisoformat(record["timestamp"])
            if ts >= cutoff:
                count += 1
    return count


def check_proposal(proposal: TradeProposal | None) -> GuardrailResult:
    """
    Pure function: given a proposal, return pass/fail + reasons.
    Split out from the node wrapper below so it's trivially unit-testable
    without needing LangGraph state at all.
    """
    if proposal is None:
        return {"passed": False, "reasons": ["No trade was proposed."]}

    reasons = []

    if proposal["ticker"] not in TICKER_ALLOWLIST:
        reasons.append(
            f"Ticker '{proposal['ticker']}' is not in the allow-list {TICKER_ALLOWLIST}."
        )

    if proposal["amount_usd"] <= 0:
        reasons.append("Order amount must be positive.")

    if proposal["amount_usd"] > MAX_ORDER_USD:
        reasons.append(
            f"Order amount ${proposal['amount_usd']} exceeds the ${MAX_ORDER_USD} cap."
        )

    trades_today = _trades_in_last_24h()
    if trades_today >= MAX_TRADES_PER_DAY:
        reasons.append(
            f"Daily trade limit reached ({trades_today}/{MAX_TRADES_PER_DAY})."
        )

    return {"passed": len(reasons) == 0, "reasons": reasons}


def guardrail_node(state: TradingState, stage: str) -> TradingState:
    """
    LangGraph node wrapper. `stage` ("pre_approval" or "pre_execution") is
    bound via a partial/lambda when the node is added to the graph (see
    graph.py) so the same underlying check function is reused for both
    guardrail points instead of duplicating logic.
    """
    result = check_proposal(state.get("proposal"))
    updates: TradingState = {
        "guardrail_result": result,
        "guardrail_stage": stage,
    }
    if not result["passed"]:
        updates["outcome"] = "rejected_by_guardrail"
    return updates
