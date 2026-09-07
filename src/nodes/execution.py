"""
execution_agent: given research_agent's analysis, drafts exactly ONE
concrete trade proposal with structured output.

Kept intentionally narrow: this node does not have tool access at all —
it can't call the order-placement tool even if it wanted to. Its only job
is to turn analysis into a single structured proposal, which then has to
survive the guardrail check and human approval before anything happens.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import json

from src.config import ANTHROPIC_API_KEY, MODEL_NAME
from src.state import TradingState

SYSTEM_PROMPT = """You draft a single trade proposal based on portfolio
analysis you're given. You have NO tool access — you cannot look anything
up or execute anything. Respond with ONLY a JSON object, no other text:

{"ticker": "...", "side": "buy" or "sell", "amount_usd": <number>, "reasoning": "..."}

If the analysis doesn't clearly support any trade, respond with:
{"ticker": null, "side": null, "amount_usd": null, "reasoning": "why no trade is proposed"}
"""


async def execution_node(state: TradingState) -> TradingState:
    model = ChatAnthropic(model=MODEL_NAME, api_key=ANTHROPIC_API_KEY)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Portfolio analysis:\n\n{state['analysis']}"),
    ]

    response = await model.ainvoke(messages)

    try:
        parsed = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        # Model didn't return clean JSON. Fail closed: no proposal rather
        # than a guess at what it meant.
        parsed = {"ticker": None, "side": None, "amount_usd": None,
                   "reasoning": "Model response was not parseable JSON; no trade proposed."}

    if not parsed.get("ticker"):
        return {"proposal": None}

    return {
        "proposal": {
            "ticker": parsed["ticker"],
            "side": parsed["side"],
            "amount_usd": float(parsed["amount_usd"]),
            "reasoning": parsed["reasoning"],
        }
    }
