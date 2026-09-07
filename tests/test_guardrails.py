"""
Unit tests for src/nodes/guardrails.py's check_proposal(), which is the
core safety logic of the whole project. Kept as plain pytest against a
pure function — no LangGraph, no LLM, no network needed to run these.
"""

import pytest

from src.nodes.guardrails import check_proposal
from src.config import MAX_ORDER_USD, TICKER_ALLOWLIST


def make_proposal(**overrides):
    base = {
        "ticker": TICKER_ALLOWLIST[0],
        "side": "buy",
        "amount_usd": 10.0,
        "reasoning": "test",
    }
    base.update(overrides)
    return base


def test_valid_proposal_passes():
    result = check_proposal(make_proposal())
    assert result["passed"] is True
    assert result["reasons"] == []


def test_none_proposal_fails():
    result = check_proposal(None)
    assert result["passed"] is False
    assert len(result["reasons"]) == 1


def test_ticker_not_on_allowlist_fails():
    result = check_proposal(make_proposal(ticker="GME"))
    assert result["passed"] is False
    assert any("allow-list" in r for r in result["reasons"])


def test_order_over_cap_fails():
    result = check_proposal(make_proposal(amount_usd=MAX_ORDER_USD + 1))
    assert result["passed"] is False
    assert any("exceeds" in r for r in result["reasons"])


def test_order_at_exact_cap_passes():
    result = check_proposal(make_proposal(amount_usd=MAX_ORDER_USD))
    assert result["passed"] is True


def test_zero_or_negative_amount_fails():
    result = check_proposal(make_proposal(amount_usd=0))
    assert result["passed"] is False
    assert any("positive" in r for r in result["reasons"])

    result = check_proposal(make_proposal(amount_usd=-5))
    assert result["passed"] is False


def test_multiple_violations_all_reported():
    # Bad ticker AND over cap at once - guardrail should report both,
    # not just short-circuit on the first failure.
    result = check_proposal(
        make_proposal(ticker="NOTALLOWED", amount_usd=MAX_ORDER_USD * 10)
    )
    assert result["passed"] is False
    assert len(result["reasons"]) >= 2
