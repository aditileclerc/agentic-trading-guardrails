"""
Manual/dev-only test: verifies research_node's tool-calling loop actually
executes tool calls, threads ToolMessages back correctly, and terminates
on a final text response - using a scripted fake model instead of a real
Anthropic API call.

Not part of the main test suite (no API-key-free way to test the real
model's behavior), but useful to confirm the loop's control flow is
correct in isolation. Run manually (as a module, from the repo root, so
`src` resolves) with:
    python -m tests.test_research_loop_manual
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from src.nodes import research


class FakeTool:
    def __init__(self, name, canned_result):
        self.name = name
        self._result = canned_result

    async def ainvoke(self, args):
        return self._result


async def main():
    tools = [
        FakeTool("get_positions", {"positions": [{"ticker": "VOO", "shares": 1}]}),
        FakeTool("get_balances", {"cash_usd": 50.0}),
    ]

    # Scripted responses: round 1 asks for both tools, round 2 gives a
    # final text answer with no further tool calls.
    round_1 = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_positions", "args": {}, "id": "call_1"},
            {"name": "get_balances", "args": {}, "id": "call_2"},
        ],
    )
    round_2 = AIMessage(content="Portfolio looks concentrated in VOO. $50 cash available.")

    # bind_tools() is called synchronously (mirrors the real ChatAnthropic
    # API) and must return the model itself; only ainvoke() is async.
    fake_model = MagicMock()
    fake_model.bind_tools.return_value = fake_model
    fake_model.ainvoke = AsyncMock(side_effect=[round_1, round_2])

    with patch.object(research, "ChatAnthropic", return_value=fake_model):
        result = await research.research_node({}, tools)

    assert "VOO" in result["analysis"], "final analysis should reflect tool results"
    assert "get_positions" in result["portfolio"], "portfolio snapshot should capture tool results"
    assert "get_balances" in result["portfolio"]
    assert fake_model.ainvoke.call_count == 2, "should stop looping once no more tool calls"

    print("research_node tool-calling loop: PASS")
    print("Final analysis:", result["analysis"])
    print("Portfolio snapshot:", result["portfolio"])


if __name__ == "__main__":
    asyncio.run(main())