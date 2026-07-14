"""Tests for the server-side approver lookup (PR-C.6, R1 high#2).

PR-C.6 closes a privilege-escalation gap the 4R review caught in
``dafi_sentinel.orchestration.graph._evaluate_approver``: the prior
implementation trusted a caller-supplied ``UserRef`` (the resume
value the approval pause sent back to the graph). A caller could
forge a ``UserRef`` with a stolen ``id`` and the ``approval:grant``
permission and the graph would happily honor the approval.

The fix threads a server-side :class:`ActorStore` through the
orchestration so ``_evaluate_approver`` looks up the approver by id
and uses the role/permission set the user store returns, NOT the
caller-supplied one. The forged ``UserRef`` is reduced to an id and
the rest is overwritten with whatever the store says.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
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
    build_investigation_graph,
)
from dafi_sentinel.security.policy import AuditSink, RedactionService, SecurityGate
from dafi_sentinel.storage.contracts import ActorStore


_FROZEN = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)


def _environment():
    """Build a workbench + gate + audits stack seeded with one evidence row.

    The seeded environment is the minimum surface the investigation
    graph needs to reach the approval pause: one evidence row that
    matches the question, one document that ranks above the threshold.
    """
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        clock=lambda: _FROZEN,
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
        timestamp=_FROZEN.replace(hour=12),
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        redacted_summary="Payment timeout crossed alert threshold",
        fields={"severity": "critical"},
    )
    workbench.evidence.save_evidence("user-1", record)
    gate = SecurityGate(
        redactor=RedactionService(),
        audits=AuditSink(clock=lambda: _FROZEN),
    )
    return workbench, gate, workbench.audits  # type: ignore[return-value]


def test_actor_store_protocol_is_exported_from_storage_contracts():
    """The ActorStore protocol is the seam the orchestrator uses for lookup."""
    from dafi_sentinel.storage.contracts import ActorStore as _ActorStore

    assert hasattr(_ActorStore, "get_user")


def test_actor_store_rejects_forged_approver():
    """A forged UserRef is overwritten with the store-returned roles/permissions."""
    # The legitimate approver the user store knows about.
    legitimate = UserRef(
        id="lead-1",
        display_name="Lead",
        roles=(Role("lead", permissions=(Permission(APPROVER_PERMISSION),)),),
    )

    # The forged resume payload: a UserRef with attacker.id but
    # legitimate's role/permission set. Pre-PR-C.6 the graph trusted
    # the resume payload, so this would have passed.
    attacker = UserRef(
        id="attacker",
        display_name="Attacker",
        roles=legitimate.roles,  # forges the permission set
    )
    assert attacker.id != legitimate.id
    # The forged payload's role carries the approval:grant permission.
    assert any(role.allows(APPROVER_PERMISSION) for role in attacker.roles)

    workbench, gate, audits = _environment()
    # The store says the attacker's id maps to an attacker WITHOUT
    # approval:grant, so the forged payload is rejected.
    store = MagicMock(spec=ActorStore)
    store.get_user.return_value = UserRef(
        id="attacker",
        display_name="Real Attacker",
        roles=(Role("intruder", permissions=()),),
    )

    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        actor_store=store,
    )

    config = {"configurable": {"thread_id": "thread-forge"}}
    initial = {
        "actor_id": "victim",
        "actor_kind": "user",
        "owner_id": "victim",
        "session_id": "session-forge",
        "question": "why did the payment timeout happen?",
        "chart_kind": "bar",
        "chart_title": "Payment timeout vs severity",
        "chart_x": "evidence_id",
        "chart_y": "severity",
        "chart_data": [("ev-incident-001", 1)],
        "chart_evidence_ids": ["ev-incident-001"],
    }
    paused = graph.invoke(initial, config=config)
    assert "__interrupt__" in paused, "graph must pause at the approval node"

    final = graph.invoke(
        Command(resume=ApprovalRequest(approved=True, approver=attacker)),
        config=config,
    )
    # The decision reason must reflect the rejection.
    assert final["approval_granted"] is False
    assert "unauthorized" in (final.get("decision_reason") or "").lower()
    # And the store MUST have been consulted with the attacker's id.
    store.get_user.assert_called_with("attacker")


def test_actor_store_consulted_on_legitimate_approval():
    """The store is consulted on legitimate approvals (not just on forgery)."""
    workbench, gate, audits = _environment()
    lead = UserRef(
        id="lead-1",
        display_name="Lead",
        roles=(Role("lead", permissions=(Permission(APPROVER_PERMISSION),)),),
    )
    store = MagicMock(spec=ActorStore)
    store.get_user.return_value = lead

    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        actor_store=store,
    )
    config = {"configurable": {"thread_id": "thread-legit"}}
    initial = {
        "actor_id": "victim",
        "actor_kind": "user",
        "owner_id": "victim",
        "session_id": "session-legit",
        "question": "why did the payment timeout happen?",
        "chart_kind": "bar",
        "chart_title": "Payment timeout vs severity",
        "chart_x": "evidence_id",
        "chart_y": "severity",
        "chart_data": [("ev-incident-001", 1)],
        "chart_evidence_ids": ["ev-incident-001"],
    }
    graph.invoke(initial, config=config)
    final = graph.invoke(
        Command(resume=ApprovalRequest(approved=True, approver=lead)),
        config=config,
    )
    assert final["approval_granted"] is True
    # The store MUST have been consulted at least once.
    assert store.get_user.called


def test_actor_store_warning_when_not_supplied(caplog):
    """When the store is not supplied, the legacy behavior runs and a warning fires."""
    import logging
    workbench, gate, audits = _environment()
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
    )
    config = {"configurable": {"thread_id": "thread-legacy"}}
    initial = {
        "actor_id": "victim",
        "actor_kind": "user",
        "owner_id": "victim",
        "session_id": "session-legacy",
        "question": "why did the payment timeout happen?",
        "chart_kind": "bar",
        "chart_title": "Payment timeout vs severity",
        "chart_x": "evidence_id",
        "chart_y": "severity",
        "chart_data": [("ev-incident-001", 1)],
        "chart_evidence_ids": ["ev-incident-001"],
    }
    with caplog.at_level(logging.WARNING, logger="dafi_sentinel.orchestration.graph"):
        graph.invoke(initial, config=config)
        graph.invoke(
            Command(
                resume=ApprovalRequest(
                    approved=True,
                    approver=UserRef(
                        id="lead-1",
                        display_name="Lead",
                        roles=(Role("lead", permissions=(Permission(APPROVER_PERMISSION),)),),
                    ),
                )
            ),
            config=config,
        )
    # The runtime warning must be present so an operator notices the
    # missing actor store before deploying.
    assert any("actor_store" in record.message for record in caplog.records)
