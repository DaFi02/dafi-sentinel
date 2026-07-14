"""LangGraph orchestration for the PR6 workbench.

The orchestration module wraps the deterministic PR1/PR2/PR3/PR4/PR5
services in a state machine. Business logic stays in the services; the
graph only composes them and adds an explicit approval pause before
controlled actions (e.g., chart rendering).

The module exposes:

* :func:`build_investigation_graph` — the compiled state graph factory.
* :class:`InvestigationState` — the TypedDict describing the graph state.
* :class:`ApprovalRequest` — the payload exchanged at the approval node.
"""
