# Agentic Trading System with Guardrails

A LangGraph-based multi-agent system that connects to Robinhood's Agentic
Trading MCP server, reasons about a portfolio, drafts trade proposals, and
requires a human approval step before any order is placed.

This project is deliberately scoped to **propose + one-tap approve**: the
agent can read your portfolio and market data and *draft* trades, but it can
never place an order without a human explicitly approving it. Autonomous
execution is an intentional non-goal for now.

## Why this exists

Robinhood's Agentic Trading MCP lets any MCP-compatible AI client read your
portfolio and place real trades on your behalf. That's powerful and also
risky by default — the agent *can* place trades without confirmation if you
let it. This project builds the missing safety layer: a deterministic,
non-LLM guardrail check plus a mandatory human-in-the-loop pause, sitting
between "agent decided to trade" and "trade actually executes."

## Architecture

```
                ┌──────────────────┐
                │  research_agent   │   reads portfolio + market data via
                │  (LLM + tools)    │   Robinhood MCP read tools
                └────────┬──────────┘
                         │ analysis
                         ▼
                ┌──────────────────┐
                │ execution_agent   │   drafts ONE concrete trade proposal
                │  (LLM, narrow)    │   {ticker, side, amount, reasoning}
                └────────┬──────────┘
                         │ proposal
                         ▼
                ┌──────────────────┐
                │  guardrail_check  │   deterministic Python, not an LLM call:
                │  (plain code)     │   order-size cap, ticker allow-list,
                └────────┬──────────┘   daily trade count
                 pass    │    fail
             ┌───────────┘    └───────────┐
             ▼                            ▼
   ┌──────────────────┐          ┌──────────────────┐
   │ human_approval    │          │  decision_log     │
   │ (interrupt())     │          │  (rejected by      │
   └────────┬──────────┘          │   guardrail)       │
    approve │  reject             └──────────────────┘
             ▼        └─────────────┐
   ┌──────────────────┐             ▼
   │ guardrail_check_2 │    ┌──────────────────┐
   │ (re-check right   │    │  decision_log     │
   │  before execution)│    │  (rejected by      │
   └────────┬──────────┘    │   human)            │
             ▼               └──────────────────┘
   ┌──────────────────┐
   │ order_execution   │   calls Robinhood MCP order-placement tool
   └────────┬──────────┘
             ▼
   ┌──────────────────┐
   │  decision_log     │   every path writes here: proposal, reasoning,
   │                   │   guardrail result, human decision, outcome
   └──────────────────┘
```

Guardrails run **twice** on purpose: once before you're even shown the
proposal (so you don't waste time approving something obviously over
limits), and again immediately before the order tool is called, in case
state changed between your approval and execution.

## Key design decisions

- **Two separate LLM nodes, not one.** `research_agent` and
  `execution_agent` are split so the execution agent's prompt can stay
  narrow ("given this analysis, propose exactly one trade") rather than
  open-ended. Narrower prompts are easier to guardrail and easier to reason
  about when something goes wrong.
- **Guardrails are plain Python, not LLM judgment.** Order-size caps and
  ticker allow-lists are boring, deterministic, and testable — see
  `tests/test_guardrails.py`. Nothing about whether a trade is "safe" is
  left to the model's discretion.
- **LangGraph's `interrupt()` for approval**, not a bolted-on CLI loop. The
  graph genuinely pauses execution and resumes exactly where it left off
  once a decision is provided, using LangGraph's checkpointing.
- **Every path logs.** Approved, rejected-by-guardrail, and
  rejected-by-human all write a structured record to the decision log —
  this is both the audit trail and the material for evaluating the system
  later.

## Repo structure

```
src/
  state.py           TypedDict schema shared across the graph
  config.py           Guardrail limits, model config, env loading
  graph.py             Builds and wires the LangGraph StateGraph
  tools/
    mcp_client.py      Connects to the Robinhood Trading MCP (or a local mock)
  nodes/
    research.py        research_agent node
    execution.py        execution_agent node
    guardrails.py        deterministic guardrail_check node (used twice)
    approval.py           interrupt()-based human approval node
    order_execution.py     calls the MCP order-placement tool
    decision_log.py         structured logging node
mock_mcp/
  server.py            Minimal mock MCP server (same tool shapes as
                       Robinhood's) for development without live access
tests/
  test_guardrails.py    Unit tests for the guardrail logic
main.py                  Entrypoint: builds the graph, runs it, handles
                         the human-approval interrupt loop from the terminal
logs/
  decisions.jsonl        Append-only decision log (created at runtime)
```

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # edit .env with your model API key and MCP endpoint
   ```

3. **Choose your MCP target**
   - **Real Robinhood MCP** (requires Agentic Trading access, which is a
     gated rollout): set `MCP_SERVER_URL=https://agent.robinhood.com/mcp/trading`
     in `.env` and authenticate per Robinhood's setup docs for your client.
   - **Local mock** (no live access needed, safe for development): run
     ```bash
     python mock_mcp/server.py
     ```
     and set `MCP_SERVER_URL=http://localhost:8000/mcp` in `.env`.

4. **Set your guardrails** in `src/config.py`:
   - `MAX_ORDER_USD` — hard cap per trade
   - `TICKER_ALLOWLIST` — tickers the agent is permitted to touch at all
   - `MAX_TRADES_PER_DAY` — daily trade count limit

5. **Run it**
   ```bash
   python main.py
   ```
   The agent will read the portfolio, draft a proposal, run it through
   guardrails, and — if it passes — pause and ask you to approve or reject
   it in the terminal before anything is executed.

## Status

Propose + one-tap approve is fully implemented. Autonomous execution,
scheduled/polling runs, and multi-rule strategies are intentionally
out of scope for now — see the "graduating" section below.

## Safety notes

- This connects to a **real brokerage account** when pointed at the live
  Robinhood MCP. Orders placed are real orders with real money.
- Keep `MAX_ORDER_USD` small and `TICKER_ALLOWLIST` short while testing.
- Nothing in this system should be read as investment advice. It is a
  demonstration of an agent architecture and a safety layer around it, not
  a trading strategy, and no performance claims should be inferred from
  it running correctly.

## Graduating beyond propose + approve

Once the approval flow has been exercised enough to trust it, natural next
steps (not yet built) would be: scheduled/polling triggers instead of
on-demand runs, softer auto-approval for trades well within limits, and
multi-rule strategies beyond a single proposed trade per run.
