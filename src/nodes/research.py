"""
research_agent: reads portfolio state via the Robinhood MCP's read tools
and produces a plain-language analysis.

This node is deliberately kept separate from execution_agent (see
execution.py) so its prompt can stay broad — "understand the current
situation" — while execution_agent's prompt stays narrow. Splitting
analysis from proposal-drafting makes each node's behavior easier to
reason about and easier to guardrail.

This node never calls the order-placement tool. It's only ever bound to
read-style tools in the SYSTEM_PROMPT's instructions, and the guardrail /
approval layer downstream is what actually prevents a stray write call —
the prompt restriction is defense-in-depth, not the only safety here.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import ANTHROPIC_API_KEY, MODEL_NAME
from src.state import TradingState

SYSTEM_PROMPT = """You are a portfolio research assistant. You have access to
tools that let you read (never modify) brokerage account data: positions,
balances, and order history.

Your job: call the relevant read tools, then produce a concise, plain-
language analysis of the current portfolio — concentration risk, cash
available, and anything notable. Do not propose a specific trade; that is
a separate agent's job. Do not call any order-placement or trade-execution
tool under any circumstances.
"""


async def research_node(state: TradingState, tools: list) -> TradingState:
    """
    LangGraph node signature: takes current state, returns a dict of state
    updates to merge in. `tools` is pre-loaded from the MCP server and
    passed in at graph-build time (see graph.py) rather than fetched fresh
    on every call.
    """
    model = ChatAnthropic(
        model=MODEL_NAME, api_key=ANTHROPIC_API_KEY
    ).bind_tools(tools)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content="Review the current portfolio and summarize its state."
        ),
    ]

    response = await model.ainvoke(messages)

    # In a fuller implementation this would loop: execute any tool calls
    # the model made, feed results back, repeat until a final text answer.
    # Kept as a single round-trip here for clarity — see README for the
    # "graduating" section on where this would be extended.
    portfolio_snapshot = {"raw_tool_calls": response.tool_calls}

    return {
        "portfolio": portfolio_snapshot,
        "analysis": response.content,
    }
