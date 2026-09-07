"""
Entrypoint: builds the graph, runs it once, and — if the graph pauses on
the human_approval interrupt — prompts for approve/reject in the terminal
and resumes the graph with that decision.

This is intentionally a simple synchronous-feeling CLI loop for a first
version (see README's "graduating" section for Slack/SMS-based approval
as a later step). The important part isn't the terminal UI, it's that the
graph is genuinely pausing/resuming via LangGraph's interrupt mechanism
rather than a manual input() call blocking inside a node.
"""

import asyncio

from langgraph.types import Command

from src.graph import build_graph


async def main():
    app = await build_graph()

    # Each run gets its own thread_id so checkpointed state doesn't bleed
    # across separate invocations.
    config = {"configurable": {"thread_id": "trading-run-1"}}

    result = await app.ainvoke({}, config=config)

    # If the graph paused on an interrupt, LangGraph surfaces it via the
    # special "__interrupt__" key rather than raising an exception.
    while "__interrupt__" in result:
        interrupt_payload = result["__interrupt__"][0].value
        print("\n" + interrupt_payload["prompt"])
        answer = input("> ").strip().lower()
        decision = "approved" if answer in ("y", "yes") else "rejected"

        result = await app.ainvoke(Command(resume=decision), config=config)

    print("\nRun complete.")
    print(f"Outcome: {result.get('outcome')}")
    if result.get("execution_result"):
        print(f"Execution result: {result['execution_result']}")


if __name__ == "__main__":
    asyncio.run(main())
