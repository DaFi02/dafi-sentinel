"""Tests for the system approver authorization contract (R3 F8).

The CRIT-6 sweeper uses the internal ``_SYSTEM_APPROVER`` identity to
resume stale paused threads with a denial decision. For the sweeper
to work, the system approver MUST pass the ``_evaluate_approver``
authorization check (it has the ``approval:grant`` permission and a
distinct id from the requestor). This module pins the contract so a
future refactor of the approver authorization surface cannot silently
break the orphan-handling sweep.

The test covers three angles:

* The system approver passes the bare ``_evaluate_approver`` check
  (the contract the sweeper relies on).
* Driving the graph end-to-end with the system approver as the
  resume value surfaces the ``approval-timeout`` decision reason.
* The system approver role carries the ``APPROVER_PERMISSION`` so
  the role/permission surface is consistent with the rest of the
  RBAC checks.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from dafi_sentinel.api.audit_enums import AuditReason
from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.domain.models import (
    Document,
    EvidenceRef,
    RedactedIncidentRecord,
    Role,
    SourceMetadata,
)
from dafi_sentinel.orchestration.graph import (
    APPROVER_PERMISSION,
    ApprovalRequest,
    _SYSTEM_APPROVER,
    _evaluate_approver,
    build_investigation_graph,
)
from dafi_sentinel.security.policy import AuditSink, RedactionService, SecurityGate


_INITIAL_CLOCK = __import__("datetime").datetime(2026, 7, 14, 15, 0, tzinfo=__import__("datetime").UTC)


def _frozen_clock():
    return _INITIAL_CLOCK


def _environment():
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        clock=_frozen_clock,
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
        timestamp=_INITIAL_CLOCK.replace(hour=12),
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        redacted_summary="Payment timeout crossed alert threshold",
        fields={"severity": "critical"},
    )
    workbench.evidence.save_evidence("user-1", record)
    gate = SecurityGate(
        redactor=RedactionService(),
        audits=AuditSink(clock=_frozen_clock),
    )
    return workbench, gate, workbench.audits  # type: ignore[return-value]


def test_orchestration_system_approver_passes_authorization_check():
    """The system approver passes the ``_evaluate_approver`` check.

    R3 F8: the CRIT-6 sweeper resumes paused threads with the system
    approver. The system approver must clear the separation-of-duties
    and permission checks so the sweeper can complete the graph
    instead of being rejected at the authz layer.
    """
    decision = _evaluate_approver(
        requestor_id="user-1",
        approver=_SYSTEM_APPROVER,
    )
    assert decision.allowed is True, (
        f"system approver must pass the authorization check; got {decision}"
    )
    assert decision.reason == AuditReason.APPROVAL_AUTHORIZED


def test_orchestration_system_approver_role_carries_approval_permission():
    """The system approver's role carries the ``APPROVER_PERMISSION``.

    The 4R review caught a hypothetical regression where the system
    approver would lose the ``approval:grant`` permission. This test
    pins the role/permission surface so a refactor that drops the
    permission fails fast (and the sweeper would not be able to
    complete a paused graph).
    """
    assert _SYSTEM_APPROVER.roles, "system approver must carry at least one role"
    role = _SYSTEM_APPROVER.roles[0]
    assert role.allows(APPROVER_PERMISSION), (
        f"system role must allow {APPROVER_PERMISSION}; got {role}"
    )


def test_orchestration_resuming_with_system_approver_surfaces_timeout_reason():
    """Resuming with the system approver surfaces the timeout reason.

    End-to-end: drive the graph to the approval pause, then resume
    with the system approver. The decision reason must be
    ``approval-timeout`` so the audit trail records the orphan
    handling, not a generic denial.
    """
    workbench, gate, audits = _environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        clock=_frozen_clock,
    )

    initial = {
        "actor_id": "user-1",
        "actor_kind": "user",
        "owner_id": "user-1",
        "session_id": "session-timeout",
        "question": "why did the payment timeout happen?",
        "chart_kind": "bar",
        "chart_title": "Payment timeout vs severity",
        "chart_x": "evidence_id",
        "chart_y": "severity",
        "chart_data": [("ev-incident-001", 1)],
        "chart_evidence_ids": ["ev-incident-001"],
    }

    paused = graph.invoke(
        initial, config={"configurable": {"thread_id": "system-approver-1"}}
    )
    assert "__interrupt__" in paused

    final = graph.invoke(
        Command(
            resume=ApprovalRequest(approved=False, approver=_SYSTEM_APPROVER),
        ),
        config={"configurable": {"thread_id": "system-approver-1"}},
    )
    assert final["approval_granted"] is False
    assert final["decision_reason"] == AuditReason.APPROVAL_TIMEOUT
    assert final.get("chart_png") is None
