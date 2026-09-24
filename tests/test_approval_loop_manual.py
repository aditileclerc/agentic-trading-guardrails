"""
Manual/dev-only test: verifies the human-approval interrupt/resume cycle
actually pauses and resumes the graph correctly - independent of whether
the LLM ever proposes a trade. As observed in practice, execution_agent's
prompt only drafts a trade when analysis "clearly supports" one, so a
live run against a balanced mock portfolio can legitimately never reach
human_approval at all. That makes a live run an unreliable way to verify
the approval mechanism itself.

This builds a graph using the exact same guardrail/approval/execution/
decision_log node functions as src/graph.py, wired identically, but
starting from a hardcoded proposal instead of research_agent ->
execution_agent. It exercises the real interrupt() + Command(resume=...)
mechanism and the real guardrail routing logic, with zero LLM calls and
zero network I/O - and points DECISION_LOG_PATH at a temp file so it
never touches the real audit log in logs/decisions.jsonl.

Not part of the main test suite (excluded via tests/conftest.py) since it
drives its own asyncio event loop rather than being pytest test_*()
functions. Run manually (as a module, from the repo root) with:
    python -m tests.test_approval_loop_manual
"""

import asyncio
import tempfile
from functools import partial
from unittest.mock import patch

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.state import TradingState
from src.config import TICKER_ALLOWLIST
from src.nodes import guardrails as guardrails_module
from src.nodes import decision_log as decision_log_module
from src.nodes.guardrails import guardrail_node
from src.nodes.approval import approval_node
from src.nodes.order_execution import order_execution_node
from src.nodes.decision_log import decision_log_node
from src.graph import _route_after_guardrail, _route_after_approval


class FakeOrderTool:
    name = "place_order"

    async def ainvoke(self, args):
        return {**args, "status": "filled (fake)"}


VALID_PROPOSAL = {
    "ticker": TICKER_ALLOWLIST[0],
    "side": "buy",
    "amount_usd": 5.0,
    "reasoning": "hardcoded proposal for exercising the approval interrupt",
}


def build_test_graph():
    """Same guardrail -> approval -> execution -> log wiring as
    src/graph.py's build_graph(), minus research_agent/execution_agent,
    so a run starts from a known proposal instead of an LLM decision."""
    graph = StateGraph(TradingState)

    graph.add_node("guardrail_pre_approval", partial(guardrail_node, stage="pre_approval"))
    graph.add_node("human_approval", approval_node)
    graph.add_node("guardrail_pre_execution", partial(guardrail_node, stage="pre_execution"))
    graph.add_node("order_execution", partial(order_execution_node, order_tool=FakeOrderTool()))
    graph.add_node("decision_log", decision_log_node)

    graph.add_edge(START, "guardrail_pre_approval")
    graph.add_conditional_edges(
        "guardrail_pre_approval", _route_after_guardrail,
        {"pass": "human_approval", "fail": "decision_log"},
    )
    graph.add_conditional_edges(
        "human_approval", _route_after_approval,
        {"approved": "guardrail_pre_execution", "rejected": "decision_log"},
    )
    graph.add_conditional_edges(
        "guardrail_pre_execution", _route_after_guardrail,
        {"pass": "order_execution", "fail": "decision_log"},
    )
    graph.add_edge("order_execution", "decision_log")
    graph.add_edge("decision_log", END)

    return graph.compile(checkpointer=MemorySaver())


async def run_one(app, thread_id: str, resume_decision: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    result = await app.ainvoke({"proposal": VALID_PROPOSAL}, config=config)

    assert "__interrupt__" in result, "expected the graph to pause for approval"
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["type"] == "trade_approval_request"
    print(f"  paused as expected: {interrupt_payload['prompt']!r}")

    result = await app.ainvoke(Command(resume=resume_decision), config=config)
    assert "__interrupt__" not in result, "graph should not pause a second time"
    return result


async def main():
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = f"{tmp_dir}/decisions.jsonl"
        # Patch the DECISION_LOG_PATH name as imported into each node module
        # (not src.config's copy) so nothing here ever touches the real
        # logs/decisions.jsonl.
        with patch.object(guardrails_module, "DECISION_LOG_PATH", log_path), \
             patch.object(decision_log_module, "DECISION_LOG_PATH", log_path):

            app = build_test_graph()

            print("Run 1: approve")
            approved = await run_one(app, "test-approve", "approved")
            assert approved["outcome"] == "executed", approved["outcome"]
            assert approved["execution_result"]["status"] == "success"
            print("  outcome:", approved["outcome"], "-", approved["execution_result"])

            print("Run 2: reject")
            rejected = await run_one(app, "test-reject", "rejected")
            assert rejected["outcome"] == "rejected_by_human", rejected["outcome"]
            assert rejected.get("execution_result") is None
            print("  outcome:", rejected["outcome"])

    print("\napproval interrupt/resume cycle: PASS")


if __name__ == "__main__":
    asyncio.run(main())
