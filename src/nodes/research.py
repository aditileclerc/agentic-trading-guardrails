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
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

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

# Hard ceiling on tool-call round-trips per run. This is a sanity limit,
# not a guardrail in the trading-safety sense (see src/nodes/guardrails.py)
# — it just stops a misbehaving model from looping forever on read-only
# calls and burning API spend.
MAX_TOOL_ROUNDS = 5


async def research_node(state: TradingState, tools: list) -> TradingState:
    """
    LangGraph node signature: takes current state, returns a dict of state
    updates to merge in. `tools` is pre-loaded from the MCP server and
    passed in at graph-build time (see graph.py) rather than fetched fresh
    on every call.

    Runs a standard tool-calling loop: ask the model, execute whatever
    tools it requested, feed the results back as ToolMessages, repeat
    until the model responds with plain text (no more tool calls) or the
    round limit is hit. Only read-style tools are exposed here in
    practice — `tools` is the full MCP tool list, but the system prompt
    instructs the model not to touch the order tool, and even if it tried,
    this node has no path to the human-approval/guardrail layer that would
    be required before an order could ever actually be placed (see
    graph.py) — the real enforcement lives there, not here.
    """
    model = ChatAnthropic(
        model=MODEL_NAME, api_key=ANTHROPIC_API_KEY
    ).bind_tools(tools)
    tools_by_name = {t.name: t for t in tools}

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content="Review the current portfolio and summarize its state."
        ),
    ]

    portfolio_snapshot: dict = {}

    for _ in range(MAX_TOOL_ROUNDS):
        response = await model.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            # No more tool calls requested - this is the final analysis.
            return {
                "portfolio": portfolio_snapshot,
                "analysis": response.content,
            }

        for call in response.tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                # Model asked for a tool that doesn't exist / wasn't
                # bound. Fail closed on that one call rather than crash
                # the whole run.
                result_content = f"Error: tool '{call['name']}' is not available."
            else:
                result = await tool.ainvoke(call["args"])
                # Keep a running snapshot of read-tool results so the
                # rest of the graph (and the decision log) has something
                # concrete to show, not just the model's prose summary.
                portfolio_snapshot[call["name"]] = result
                result_content = str(result)

            messages.append(
                ToolMessage(content=result_content, tool_call_id=call["id"])
            )

    # Round limit hit without a final text response. Fail closed: no
    # confident analysis rather than guessing from partial data.
    return {
        "portfolio": portfolio_snapshot,
        "analysis": (
            "Research agent did not reach a final analysis within "
            f"{MAX_TOOL_ROUNDS} tool-call rounds."
        ),
    }