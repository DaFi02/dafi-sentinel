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
    APPROVER_PERMISSION,
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


def _approver_user_ref(*, with_permission: bool = True) -> UserRef:
    """Build a UserRef carrying the approver role.

    The CRIT-2 fix requires the approver to be a separate user with the
    ``approval:grant`` permission. ``with_permission=False`` seeds the
    same user id without the permission so the test for the
    unauthorized-approver path can reuse the helper.
    """
    roles: tuple[Role, ...] = (
        Role("approver", permissions=(Permission(APPROVER_PERMISSION),)),
    ) if with_permission else (Role("unprivileged", permissions=()),)
    return UserRef(id="user-2", display_name="Other", roles=roles)


def _run_with_approval(
    graph: Any,
    config: dict[str, Any],
    initial: InvestigationState,
    *,
    approved: bool,
    approver: UserRef | None = None,
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

    The CRIT-2 fix changed the resume value from a bare ``approver_id``
    to a full ``UserRef``; the default approver is a distinct user with
    the ``approval:grant`` permission so the happy path is always a
    real human approver, not a self-approval.
    """
    first = graph.invoke(initial, config=config)
    if "__interrupt__" not in first:
        # Graph ran end-to-end without an approval pause.
        return cast(dict[str, Any], first)

    approver_ref = approver if approver is not None else _approver_user_ref()
    return cast(
        dict[str, Any],
        graph.invoke(
            Command(resume=ApprovalRequest(approved=approved, approver=approver_ref)),
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
    # The CRIT-2 fix requires a distinct human approver (user-2 by
    # default in the test helper) with the ``approval:grant``
    # permission; the approver id is propagated to the finalize node.
    assert final["approval_granted"] is True
    assert final["approval_approver"] == "user-2"
    assert final["decision_reason"] == "approved-by-user-2"


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

    # The CRIT-2 fix requires a distinct approver with the
    # ``approval:grant`` permission. The denial scenario uses the
    # default approver (user-2 with the approver role) and refuses
    # the controlled action.
    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "deny-1"}},
        initial=_initial_state(session_id="session-deny"),
        approved=False,
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

    # The CRIT-2 fix routes the approval audit through the separate
    # approver (user-2) so the trail of who granted the controlled
    # action is attributable to a distinct human. The other stateful
    # actions (inspect, retrieve, render_chart, finalize) are still
    # attributed to the requestor (user-1).
    by_action: dict[str, list[dict[str, Any]]] = {}
    for record in final["audit_records"]:
        by_action.setdefault(record["action"], []).append(record)

    for action in ("orchestration.inspect", "orchestration.retrieve", "orchestration.render_chart", "orchestration.finalize"):
        for record in by_action.get(action, ()):
            assert record["actor_id"] == "user-1", f"{action} must be attributed to the requestor"
    for record in by_action.get("orchestration.approval", ()):
        assert record["actor_id"] == "user-2", (
            "orchestration.approval must be attributed to the approver, not the requestor"
        )


def test_orchestration_state_is_typed_and_total_false():
    """The state TypedDict is total=False so every node can return a partial update."""
    annotations = InvestigationState.__annotations__
    # Spot-check the keys the implementation actually writes/reads.
    assert "approval_granted" in annotations
    assert "approval_approver" in annotations
    assert "decision_reason" in annotations
    assert "chart_png" in annotations
    assert "audit_records" in annotations


# --------------------------------------------------------------------------- #
# Approver authorization (CRIT-2) — separation of duties + permission check
# --------------------------------------------------------------------------- #


def test_orchestration_approval_audit_attributes_actor_to_approver_not_requester():
    """The approval audit record's actor is the approver, not the requestor.

    The CRIT-2 fix routes the approval audit through the approver so
    the trail of who granted (or attempted to grant) the controlled
    action is attributable to a separate human. Without this, a
    requestor could self-approve and still show up as the actor of the
    approval record, defeating the separation-of-duties invariant.
    """
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "approver-actor"}},
        initial=_initial_state(),
        approved=True,
    )

    approval_audits = [r for r in final["audit_records"] if r["action"] == "orchestration.approval"]
    assert approval_audits, "the approval node must write an audit record"
    # The approver audit actor is the separate human approver (user-2),
    # NOT the requestor (user-1). Other audits still attribute the
    # requestor as the actor (inspect, retrieve, render_chart, finalize).
    assert approval_audits[0]["actor_id"] == "user-2"


def test_orchestration_denies_self_approval():
    """A requestor cannot approve their own request.

    The CRIT-2 fix (separation of duties) refuses the approval when the
    resume value identifies the requestor as the approver. The graph
    records the refusal as ``approval-self-or-unauthorized`` and skips
    the chart render.
    """
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    # The requestor is user-1 (set by _initial_state); the approver is
    # the same user with the approval:grant permission. The graph MUST
    # refuse this combination.
    self_approver = UserRef(
        id="user-1",
        display_name="Self",
        roles=(Role("approver", permissions=(Permission(APPROVER_PERMISSION),)),),
    )
    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "self-approve"}},
        initial=_initial_state(),
        approved=True,
        approver=self_approver,
    )

    # The chart was not rendered because the approval was refused.
    assert final.get("chart_png") is None
    assert final["approval_granted"] is False
    assert final["decision_reason"] == "approval-self-or-unauthorized"

    # The audit trail carries the refusal decision so a reviewer can
    # see who tried to self-approve.
    approval_audits = [r for r in final["audit_records"] if r["action"] == "orchestration.approval"]
    assert approval_audits
    decision = approval_audits[0]["decision"]
    assert decision["allowed"] is False
    assert decision["reason"] == "approval-self-or-unauthorized"


def test_orchestration_denies_approval_without_permission():
    """An approver without ``approval:grant`` is refused.

    The CRIT-2 fix also requires the approver to carry the
    ``approval:grant`` permission. A separate user without the
    permission is refused with the same audit reason
    ``approval-self-or-unauthorized``; this is the second half of the
    separation-of-duties check (identity AND permission).
    """
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    # user-2 exists but without the approver role/permission.
    unprivileged_approver = _approver_user_ref(with_permission=False)
    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "no-perm"}},
        initial=_initial_state(),
        approved=True,
        approver=unprivileged_approver,
    )

    assert final.get("chart_png") is None
    assert final["approval_granted"] is False
    assert final["decision_reason"] == "approval-self-or-unauthorized"

    approval_audits = [r for r in final["audit_records"] if r["action"] == "orchestration.approval"]
    assert approval_audits
    decision = approval_audits[0]["decision"]
    assert decision["allowed"] is False
    assert decision["reason"] == "approval-self-or-unauthorized"


# --------------------------------------------------------------------------- #
# Paused-graph TTL sweeper (CRIT-6) — orphan handling
# --------------------------------------------------------------------------- #


def test_orchestration_sweeps_stale_paused_graphs_after_ttl():
    """A paused graph older than the TTL is finalized with ``approval-timeout``.

    The CRIT-6 fix addresses the orphan-handling gap: a paused
    investigation that nobody resumes would otherwise sit in the
    InMemorySaver forever. The sweeper resumes stale threads with a
    denial decision so the finalize node writes the
    ``approval-timeout`` audit reason and the operator can see which
    investigations were abandoned.
    """
    import time

    from dafi_sentinel.orchestration.graph import sweep_stale_pauses

    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    config = {"configurable": {"thread_id": "ttl-1"}}
    initial = _initial_state()

    # Pause the graph at the approval node.
    paused = graph.invoke(initial, config=config)
    assert "__interrupt__" in paused
    assert graph.get_state(config) is not None

    # The TTL is 0 seconds: the paused thread is immediately stale.
    # The sweeper resumes it with a denial, the finalize node records
    # ``approval-timeout``, and the chart is not rendered.
    time.sleep(0.01)  # ensure the checkpoint timestamp is older than the TTL
    swept = sweep_stale_pauses(
        graph,
        thread_ids=["ttl-1"],
        ttl_seconds=0,
    )
    assert swept == 1, f"sweeper should sweep exactly the stale thread; got {swept}"

    # The thread is now finalized; the snapshot shows the timeout
    # reason in the decision.
    snapshot = graph.get_state(config)
    assert snapshot is not None
    final_state = snapshot.values
    assert final_state.get("chart_png") is None
    assert final_state.get("decision_reason") == "approval-timeout"

    # An audit record carries the timeout denial so reviewers can
    # see which investigation was abandoned.
    actions = [record["action"] for record in final_state["audit_records"]]
    assert "orchestration.finalize" in actions


def test_orchestration_sweeper_skips_fresh_paused_graphs():
    """A paused graph within the TTL is NOT swept.

    The sweeper must not finalize threads that are still inside their
    TTL window; the operator only wants orphans, not in-flight
    investigations. This test pins the contract.
    """
    from dafi_sentinel.orchestration.graph import sweep_stale_pauses

    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    config = {"configurable": {"thread_id": "fresh-1"}}
    initial = _initial_state()

    # Pause the graph.
    paused = graph.invoke(initial, config=config)
    assert "__interrupt__" in paused

    # A 1-hour TTL leaves a freshly paused thread far inside the window.
    swept = sweep_stale_pauses(
        graph,
        thread_ids=["fresh-1"],
        ttl_seconds=3600,
    )
    assert swept == 0, f"fresh thread must not be swept; got {swept}"

    # The thread is still paused.
    snapshot = graph.get_state(config)
    assert snapshot is not None
    assert "__interrupt__" in snapshot.values or snapshot.next, (
        "thread should remain paused after a no-op sweep"
    )


# --------------------------------------------------------------------------- #
# Audit id uniqueness — re-execution must not collide (CRIT-5)
# --------------------------------------------------------------------------- #


def test_orchestration_audit_ids_are_unique_across_re_invocations():
    """Re-invoking the same graph with the same session_id must yield distinct audit ids.

    The 4R review (CRIT-5, R1-003=R4-001) caught the prior
    ``audit-orchestration-{session_id}-{action}`` scheme: re-running the
    graph would either crash the audit repository on the duplicate id or
    silently overwrite the prior record. The fix swaps the deterministic
    id for a per-call token so re-execution is safe.
    """
    workbench, gate, audits = _build_environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )

    first = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "audit-ids-1"}},
        initial=_initial_state(),
        approved=True,
    )
    second = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "audit-ids-2"}},
        initial=_initial_state(),
        approved=True,
    )

    first_ids = [record["id"] for record in first["audit_records"]]
    second_ids = [record["id"] for record in second["audit_records"]]
    assert first_ids, "first run must produce audit records"
    assert second_ids, "second run must produce audit records"
    assert set(first_ids).isdisjoint(second_ids), (
        f"audit ids collided across re-invocations: {first_ids} vs {second_ids}"
    )
