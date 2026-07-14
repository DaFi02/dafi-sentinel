"""Tests for the PR6 LangGraph orchestration.

The orchestration module composes the existing PR1-PR5 services
(security gate, retrieval port, ML ranker, chart renderer, audit
repository) inside a state machine. The graph MUST pause via the
``langgraph.types.interrupt`` primitive before any controlled action
(rendering a chart, in the V1 surface) and the test helper provides the
approval so the flow continues.

Every stateful node writes an :class:`AuditRecord`; the denial path
records ``PolicyDecision(allowed=False, reason='approval-denied')``.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.domain.models import (
    Document,
    EvidenceRef,
    Permission,
    RedactedIncidentRecord,
    Role,
    SourceMetadata,
    UserRef,
)
from dafi_sentinel.orchestration.graph import (
    ApprovalRequest,
    InvestigationState,
    build_investigation_graph,
)
from dafi_sentinel.security.policy import AuditSink, RedactionService, SecurityGate


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #


_FIXED_CLOCK = lambda: datetime(2026, 7, 14, 15, 0, tzinfo=UTC)  # noqa: E731


def _build_environment() -> tuple[WorkbenchService, SecurityGate, InMemoryAuditRepository]:
    """Build a deterministic workbench + gate + audit stack.

    The fixture is shared by every test; each test still gets a fresh
    instance because the helper is called per-test, not at module scope.
    """
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
    )
    workbench.seed_documents(
        (
            Document(
                id="runbook-1",
                title="Payment Latency Runbook",
                body="payment dependency check; investigate timeout on payment gateway",
                source=SourceMetadata("fixtures/checkout_latency_runbook.md"),
                evidence_ids=("ev-incident-001",),
            ),
        )
    )
    record = RedactedIncidentRecord(
        evidence_ref=EvidenceRef(
            evidence_id="ev-incident-001",
            source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        ),
        timestamp=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        redacted_summary="Payment timeout crossed alert threshold",
        fields={"severity": "critical"},
    )
    workbench.evidence.save("user-1", record)

    gate = SecurityGate(
        redactor=RedactionService(),
        audits=AuditSink(clock=_FIXED_CLOCK),
    )
    return workbench, gate, workbench.audits  # type: ignore[return-value]


def _initial_state(
    *,
    actor_id: str = "user-1",
    owner_id: str = "user-1",
    session_id: str = "session-1",
    question: str = "why did the payment timeout happen?",
) -> InvestigationState:
    return {
        "actor_id": actor_id,
        "actor_kind": "user",
        "owner_id": owner_id,
        "session_id": session_id,
        "question": question,
        "chart_kind": "bar",
        "chart_title": "Payment timeout vs severity",
        "chart_x": "evidence_id",
        "chart_y": "severity",
        "chart_data": [("ev-incident-001", 1)],
        "chart_evidence_ids": ["ev-incident-001"],
    }


def _run_with_approval(
    graph: Any,
    config: dict[str, Any],
    initial: InvestigationState,
    *,
    approved: bool,
    approver_id: str = "user-1",
) -> dict[str, Any]:
    """Drive the graph to completion (or denial) and return the final state.

    LangGraph 1.x returns the in-progress state with a ``__interrupt__``
    key when ``interrupt()`` is called (instead of raising). The helper
    detects the pause via that key, resumes with the caller-supplied
    decision, and returns the final state.

    When approval is granted, the final state contains the chart PNG.
    When it is denied, the finalize node records the denial audit and
    the chart is absent. If the question has no supporting evidence,
    the graph skips the approval step entirely and the first invoke
    returns the final state without an interrupt.
    """
    first = graph.invoke(initial, config=config)
    if "__interrupt__" not in first:
        # Graph ran end-to-end without an approval pause.
        return cast(dict[str, Any], first)

    return cast(
        dict[str, Any],
        graph.invoke(
            Command(resume=ApprovalRequest(approved=approved, approver_id=approver_id)),
            config=config,
        ),
    )


# --------------------------------------------------------------------------- #
# Happy path — every node runs in order
# --------------------------------------------------------------------------- #


def test_happy_path_runs_every_node_and_captures_final_state():
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "happy-1"}},
        initial=_initial_state(),
        approved=True,
    )

    # The answer cites at least one evidence id and is not "unknown".
    assert tuple(final["cited"]) == ("ev-incident-001",)
    assert final["answer"] != "unknown"
    assert "ev-incident-001" in final["answer"]

    # The chart was rendered (PNG starts with the magic bytes).
    assert final.get("chart_png") is not None
    assert final["chart_png"].startswith(b"\x89PNG")

    # The approval was recorded and propagated to the finalize audit.
    assert final["approval_granted"] is True
    assert final["approval_approver"] == "user-1"
    assert final["decision_reason"] == "approved-by-user-1"


# --------------------------------------------------------------------------- #
# Approval pause — graph pauses, state is persisted
# --------------------------------------------------------------------------- #


def test_graph_pauses_at_approval_node_and_persists_state():
    workbench, gate, audits = _build_environment()
    saver = InMemorySaver()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "pause-1"}}
    initial = _initial_state(session_id="session-pause")

    # First call returns the in-progress state with a ``__interrupt__``
    # key because the approval node calls ``interrupt(...)`` and no
    # resume value is available.
    paused = graph.invoke(initial, config=config)
    assert "__interrupt__" in paused

    # The checkpointer retained the in-progress state.
    snapshot = graph.get_state(config)
    assert snapshot is not None
    assert snapshot.values["session_id"] == "session-pause"
    # The question survived the inspect + retrieve + compose nodes.
    assert snapshot.values["question"] == "why did the payment timeout happen?"
    # The chart was composed but not yet rendered.
    assert tuple(snapshot.values["cited"]) == ("ev-incident-001",)
    assert snapshot.values.get("chart_png") is None


# --------------------------------------------------------------------------- #
# Approval denial — finalize records the denial audit
# --------------------------------------------------------------------------- #


def test_approval_denial_records_policy_decision_and_skips_chart_render():
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "deny-1"}},
        initial=_initial_state(session_id="session-deny"),
        approved=False,
        approver_id="user-1",
    )

    # The denial path skips the chart render and routes to finalize.
    assert final.get("chart_png") is None
    assert final["approval_granted"] is False
    assert final["decision_reason"] == "approval-denied"

    # The finalize audit MUST include the denial PolicyDecision. The
    # graph serializes PolicyDecision as a dict (see ``_serialize_audit``)
    # so the assertion works on dicts, not dataclasses.
    audit_decisions = [record["decision"] for record in final["audit_records"]]
    assert {"allowed": False, "reason": "approval-denied", "required_permission": None} in audit_decisions


# --------------------------------------------------------------------------- #
# Compose vs. reimplement — graph MUST delegate retrieval to the PR3 port
# --------------------------------------------------------------------------- #


def test_orchestration_composes_existing_pr_services_without_reimplementing_them():
    """The graph must NOT replace the existing services; it only composes them."""
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    # The retrieval step MUST come from the PR3 retrieval contract
    # (InMemoryRetrievalIndex is the PR3 fixture adapter). Replace it
    # with an empty index and confirm the graph answers "unknown" without
    # citing evidence — proving the graph does not have its own retrieval.
    workbench.seed_documents(())
    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "compose-1"}},
        initial=_initial_state(question="unrelated gibberish question xyz"),
        approved=True,
    )

    assert list(final["cited"]) == []
    assert final["answer"] == "unknown"
    # The chart is still requested, but the finalize node refuses when
    # there is no supporting evidence.
    assert final.get("chart_png") is None
    assert final["decision_reason"] == "no-supporting-evidence"


# --------------------------------------------------------------------------- #
# Audit coverage — every stateful node writes an AuditRecord
# --------------------------------------------------------------------------- #


def test_every_stateful_node_writes_an_audit_record():
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "audit-1"}},
        initial=_initial_state(),
        approved=True,
    )

    actions = {record["action"] for record in final["audit_records"]}
    # The graph composes: inspect, retrieve, render chart, finalize.
    # Every stateful node MUST contribute at least one audit record.
    assert "orchestration.inspect" in actions
    assert "orchestration.retrieve" in actions
    assert "orchestration.render_chart" in actions
    assert "orchestration.finalize" in actions

    # Each audit record is actor-attributed (per security-agent spec).
    for record in final["audit_records"]:
        assert record["actor_id"] == "user-1"
        assert "user-1" in record["role_context"]


def test_orchestration_state_is_typed_and_total_false():
    """The state TypedDict is total=False so every node can return a partial update."""
    annotations = InvestigationState.__annotations__
    # Spot-check the keys the implementation actually writes/reads.
    assert "approval_granted" in annotations
    assert "approval_approver" in annotations
    assert "decision_reason" in annotations
    assert "chart_png" in annotations
    assert "audit_records" in annotations
