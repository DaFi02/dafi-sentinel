"""Tests for the audit action and reason enums (R2 high#3).

The 4R review caught that the audit log carried 9 distinct action
strings and ~10 distinct reason strings as bare literals spread across
:mod:`dafi_sentinel.api.services`, :mod:`dafi_sentinel.orchestration.graph`,
and :mod:`dafi_sentinel.api.app`. A typo at any of those call sites
silently produced a new action/reason and the suite would not notice.
The fix lifts the canonical strings into :mod:`dafi_sentinel.api.audit_enums`
so the wire format is unchanged but a typo is impossible.

This module pins the contract:

* Every canonical action/reason has a single source of truth.
* The :class:`AuditRecord` round-trips the enum value as a plain string
  so the on-disk audit log and the ``/audits`` payload format are
  unchanged.
* The enums are exported from the public API surface so a future
  caller cannot reach for a bare literal.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from dafi_sentinel.api.audit_enums import AuditAction, AuditReason
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


def _approver() -> UserRef:
    return UserRef(
        id="user-2",
        display_name="Other",
        roles=(Role("approver", permissions=(Permission(APPROVER_PERMISSION),)),),
    )


# --------------------------------------------------------------------------- #
# Enum surface — the canonical set
# --------------------------------------------------------------------------- #


def test_audit_action_enum_contains_canonical_actions():
    """The enum covers every action the workbench emits."""
    assert AuditAction.QA_ANSWER.value == "qa.answer"
    assert AuditAction.CHART_RENDER.value == "chart.render"
    assert AuditAction.SESSION_LOGIN.value == "session.login"
    assert AuditAction.SESSION_LOGOUT.value == "session.logout"
    assert AuditAction.ORCHESTRATION_INSPECT.value == "orchestration.inspect"
    assert AuditAction.ORCHESTRATION_RETRIEVE.value == "orchestration.retrieve"
    assert AuditAction.ORCHESTRATION_APPROVAL.value == "orchestration.approval"
    assert AuditAction.ORCHESTRATION_RENDER_CHART.value == "orchestration.render_chart"
    assert AuditAction.ORCHESTRATION_FINALIZE.value == "orchestration.finalize"


def test_audit_reason_enum_contains_canonical_reasons():
    """The enum covers the static reasons the workbench emits."""
    assert AuditReason.LOGIN_SUCCEEDED.value == "login succeeded"
    assert AuditReason.LOGOUT_SUCCEEDED.value == "logout succeeded"
    assert AuditReason.EVIDENCE_CITED.value == "evidence cited"
    assert AuditReason.NO_SUPPORTING_EVIDENCE.value == "no supporting evidence"
    assert AuditReason.APPROVAL_DENIED.value == "approval-denied"
    assert AuditReason.APPROVAL_SELF_OR_UNAUTHORIZED.value == "approval-self-or-unauthorized"
    assert AuditReason.APPROVAL_TIMEOUT.value == "approval-timeout"


def test_audit_action_enum_is_a_str_subclass():
    """The enum values serialize as plain strings.

    The audit store persists the action as a string column. The enum
    must round-trip through ``.value`` (or direct equality with a
    string) without manual unwrapping at every call site, so callers
    and the database see the same wire format.
    """
    assert AuditAction.QA_ANSWER.value == "qa.answer"
    assert AuditReason.APPROVAL_DENIED.value == "approval-denied"
    # Direct string equality (the common comparison form) works because
    # the enum mixes in ``str``; the wire format is unchanged.
    assert AuditAction.QA_ANSWER == "qa.answer"
    assert AuditReason.APPROVAL_DENIED == "approval-denied"


# --------------------------------------------------------------------------- #
# Workbench service — every audit record uses the enum
# --------------------------------------------------------------------------- #


def test_workbench_service_login_uses_session_login_enum():
    """``record_login`` writes the canonical session.login action."""
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        clock=_frozen_clock,
    )
    workbench.record_login(actor_id="user-1", session_id="sess-1")
    record = workbench.audits.all()[0]  # type: ignore[attr-defined]
    assert record.action == AuditAction.SESSION_LOGIN
    assert record.action == "session.login"  # wire format unchanged
    assert record.decision.reason == AuditReason.LOGIN_SUCCEEDED


def test_workbench_service_logout_uses_session_logout_enum():
    """``record_logout`` writes the canonical session.logout action."""
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        clock=_frozen_clock,
    )
    workbench.record_logout(actor_id="user-1", session_id="sess-1")
    record = workbench.audits.all()[0]  # type: ignore[attr-defined]
    assert record.action == AuditAction.SESSION_LOGOUT
    assert record.decision.reason == AuditReason.LOGOUT_SUCCEEDED


# --------------------------------------------------------------------------- #
# Graph — orchestration actions use the enum
# --------------------------------------------------------------------------- #


def test_orchestration_approval_uses_canonical_approval_enum_action():
    """The orchestration approval action is the canonical enum value.

    Drives the graph end-to-end so the audit log accumulates the full
    set of actions; every action string MUST equal its enum value.
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
        "session_id": "session-1",
        "question": "why did the payment timeout happen?",
        "chart_kind": "bar",
        "chart_title": "Payment timeout vs severity",
        "chart_x": "evidence_id",
        "chart_y": "severity",
        "chart_data": [("ev-incident-001", 1)],
        "chart_evidence_ids": ["ev-incident-001"],
    }

    first = graph.invoke(initial, config={"configurable": {"thread_id": "enum-1"}})
    if "__interrupt__" in first:
        from langgraph.types import Command

        first = graph.invoke(
            Command(resume=ApprovalRequest(approved=True, approver=_approver())),
            config={"configurable": {"thread_id": "enum-1"}},
        )

    actions = {record["action"] for record in first["audit_records"]}
    assert AuditAction.ORCHESTRATION_INSPECT in actions
    assert AuditAction.ORCHESTRATION_RETRIEVE in actions
    assert AuditAction.ORCHESTRATION_APPROVAL in actions
    assert AuditAction.ORCHESTRATION_RENDER_CHART in actions
    assert AuditAction.ORCHESTRATION_FINALIZE in actions
