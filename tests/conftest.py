"""
test_research_loop_manual.py and test_approval_loop_manual.py are
scripted, run-by-hand checks (see each file's own docstring) — neither
has test_*() functions for pytest to run, and both pull in dependencies
(langchain_core / langgraph) that aren't dependencies of the actual test
suite (tests/test_guardrails.py runs with zero LLM/graph packages
installed). Left uncollected so a bare `pytest` doesn't require those
packages.
"""

collect_ignore = ["test_research_loop_manual.py", "test_approval_loop_manual.py"]
