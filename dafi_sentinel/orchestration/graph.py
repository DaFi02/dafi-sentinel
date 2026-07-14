"""Investigation state machine for the PR6 workbench (placeholder).

The full implementation ships in the follow-up work-unit commits. This
stub exists so the PR6 boundary guard can confirm the surface landed;
the imports below are the langgraph primitives the implementation will
exercise (StateGraph, interrupt, Command, InMemorySaver).
"""

from langgraph.checkpoint.memory import InMemorySaver  # noqa: F401  (PR6 surface marker)
from langgraph.graph import StateGraph  # noqa: F401  (PR6 surface marker)
from langgraph.types import Command, interrupt  # noqa: F401  (PR6 surface marker)


def build_investigation_graph(*args, **kwargs):  # pragma: no cover - stub
    raise NotImplementedError("PR6 state machine lands in the follow-up commit")
