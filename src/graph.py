"""
Builds and compiles the LangGraph StateGraph:

research_agent -> execution_agent -> guardrail_check(pre_approval)
    -> [fail] -> decision_log -> END
    -> [pass] -> human_approval
        -> [rejected] -> decision_log -> END
        -> [approved] -> guardrail_check(pre_execution)
            -> [fail] -> decision_log -> END
            -> [pass] -> order_execution -> decision_log -> END

See README.md for the diagram and the reasoning behind running the
guardrail check twice and keeping research/execution as separate nodes.
"""

from functools import partial

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.state import TradingState
from src.tools.mcp_client import load_mcp_tools
from src.nodes.research import research_node
from src.nodes.execution import execution_node
from src.nodes.guardrails import guardrail_node
from src.nodes.approval import approval_node
from src.nodes.order_execution import order_execution_node
from src.nodes.decision_log import decision_log_node


def _route_after_guardrail(state: TradingState) -> str:
    """Shared routing logic for both guardrail checkpoints."""
    return "pass" if state["guardrail_result"]["passed"] else "fail"


def _route_after_approval(state: TradingState) -> str:
    return "approved" if state["human_decision"] == "approved" else "rejected"


async def build_graph():
    """
    Async because loading MCP tools requires an async round-trip to the
    server. Returns a compiled, checkpointed graph ready to invoke.
    """
    tools = await load_mcp_tools()

    # Locate the single order-placement tool by name so order_execution.py
    # only ever receives that one tool, never the full read+write tool list.
    order_tool = next(t for t in tools if t.name == "place_order")

    graph = StateGraph(TradingState)

    graph.add_node("research_agent", partial(research_node, tools=tools))
    graph.add_node("execution_agent", execution_node)
    graph.add_node("guardrail_pre_approval", partial(guardrail_node, stage="pre_approval"))
    graph.add_node("human_approval", approval_node)
    graph.add_node("guardrail_pre_execution", partial(guardrail_node, stage="pre_execution"))
    graph.add_node("order_execution", partial(order_execution_node, order_tool=order_tool))
    graph.add_node("decision_log", decision_log_node)

    graph.add_edge(START, "research_agent")
    graph.add_edge("research_agent", "execution_agent")
    graph.add_edge("execution_agent", "guardrail_pre_approval")

    graph.add_conditional_edges(
        "guardrail_pre_approval",
        _route_after_guardrail,
        {"pass": "human_approval", "fail": "decision_log"},
    )

    graph.add_conditional_edges(
        "human_approval",
        _route_after_approval,
        {"approved": "guardrail_pre_execution", "rejected": "decision_log"},
    )

    graph.add_conditional_edges(
        "guardrail_pre_execution",
        _route_after_guardrail,
        {"pass": "order_execution", "fail": "decision_log"},
    )

    graph.add_edge("order_execution", "decision_log")
    graph.add_edge("decision_log", END)

    # In-memory checkpointing is enough for local, single-session runs.
    # Swap for a persistent checkpointer (e.g. SQLite/Postgres) if runs
    # need to survive a process restart while paused on interrupt().
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
