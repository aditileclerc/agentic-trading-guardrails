"""
Central configuration, including the guardrail limits.

These limits are intentionally kept in one plain, readable place — not
scattered across nodes, and not something the LLM ever sees or can
influence. Tightening these is the main lever for how much real risk this
system carries.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME", "claude-sonnet-4-5")

# --- MCP ---
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")

# --- Guardrails ---
# Hard cap on the dollar amount of any single proposed trade.
# Keep this small (e.g. $10-25) while trusting the system.
MAX_ORDER_USD = float(os.environ.get("MAX_ORDER_USD", "25"))

# Only these tickers can ever be proposed or executed. Anything else is
# rejected automatically regardless of the LLM's reasoning.
TICKER_ALLOWLIST = os.environ.get("TICKER_ALLOWLIST", "VOO,AAPL,MSFT").split(",")

# Maximum number of trades (approved + executed) allowed in a rolling
# 24-hour window, tracked via the decision log.
MAX_TRADES_PER_DAY = int(os.environ.get("MAX_TRADES_PER_DAY", "3"))

# --- Logging ---
DECISION_LOG_PATH = os.environ.get("DECISION_LOG_PATH", "logs/decisions.jsonl")
