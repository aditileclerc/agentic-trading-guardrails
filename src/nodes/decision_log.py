"""
decision_log: terminal node reached by every path through the graph
(rejected by guardrail, rejected by human, executed, or execution failed).

Writes one JSON line per run to DECISION_LOG_PATH. This is both the audit
trail referenced in the project description and the data source
guardrails.py reads from to enforce the daily trade cap.
"""

import json
import os
from datetime import datetime, timezone

from src.config import DECISION_LOG_PATH
from src.state import TradingState


def decision_log_node(state: TradingState) -> TradingState:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analysis": state.get("analysis"),
        "proposal": state.get("proposal"),
        "guardrail_result": state.get("guardrail_result"),
        "human_decision": state.get("human_decision"),
        "execution_result": state.get("execution_result"),
        "outcome": state.get("outcome"),
    }

    os.makedirs(os.path.dirname(DECISION_LOG_PATH), exist_ok=True)
    with open(DECISION_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    return {}
