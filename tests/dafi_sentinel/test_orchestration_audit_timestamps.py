"""Tests for the clock-injected audit timestamp contract (R3 F2).

The 4R review flagged that ``_build_audit_record`` and
``WorkbenchService._record_audit`` called ``datetime.now(UTC)`` directly,
which makes audit timestamps non-deterministic and breaks replay-based
review. The fix threads a ``clock: Callable[[], datetime]`` parameter
through both surfaces; this module pins the contract:

* A frozen clock yields identical timestamps across consecutive audit
  records inside the same graph run.
* Advancing the clock between runs yields strictly increasing timestamps
  so reviewers can reconstruct the ordering of related events.

The tests are split into a graph-level test (driving
``build_investigation_graph`` with a frozen clock) and a
service-level test (calling ``WorkbenchService._record_audit`` directly)
so the contract is enforced on both call sites.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.domain.models import (
    Document,
    EvidenceRef,
    RedactedIncidentRecord,
    SourceMetadata,
)
from dafi_sentinel.orchestration.graph import (
    APPROVER_PERMISSION,
    ApprovalRequest,
    build_investigation_graph,
)
from dafi_sentinel.security.policy import AuditSink, RedactionService, SecurityGate


# --------------------------------------------------------------------------- #
# Test fixtures (mirror test_orchestration.py helpers; kept local to avoid a
# cross-module coupling that would force an import cycle through conftest).
# --------------------------------------------------------------------------- #


_INITIAL_CLOCK = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)


def _frozen_clock() -> datetime:
    """Return a fixed timestamp for the first half of the test.

    The closure satisfies the ``Callable[[], datetime]`` contract that the
    clock-injection pattern documents. Mutating the underlying
    ``_clock_now`` slot (see parametrized cases) advances the clock.
    """
    return _INITIAL_CLOCK


def _environment_with_clock(
    clock,
) -> tuple[WorkbenchService, SecurityGate, InMemoryAuditRepository]:
    """Build a deterministic workbench + gate + audit stack with the supplied clock.

    The workbench hands the clock to the audit recorder; the gate keeps
    its own fixed clock (the security-gate audit already had a
    ``clock`` parameter in the archived PR1 contract).
    """
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        clock=clock,
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
        audits=AuditSink(clock=clock),
    )
    return workbench, gate, workbench.audits  # type: ignore[return-value]


def _initial_state(
    *,
    actor_id: str = "user-1",
    owner_id: str = "user-1",
    session_id: str = "session-1",
) -> dict:
    return {
        "actor_id": actor_id,
        "actor_kind": "user",
        "owner_id": owner_id,
        "session_id": session_id,
        "question": "why did the payment timeout happen?",
        "chart_kind": "bar",
        "chart_title": "Payment timeout vs severity",
        "chart_x": "evidence_id",
        "chart_y": "severity",
        "chart_data": [("ev-incident-001", 1)],
        "chart_evidence_ids": ["ev-incident-001"],
    }


def _approver_user_ref():
    from dafi_sentinel.domain.models import Permission, Role, UserRef

    return UserRef(
        id="user-2",
        display_name="Other",
        roles=(Role("approver", permissions=(Permission(APPROVER_PERMISSION),)),),
    )


def _run_with_approval(graph, config, initial, *, approved: bool) -> dict:
    first = graph.invoke(initial, config=config)
    if "__interrupt__" not in first:
        return cast(dict, first)
    return cast(
        dict,
        graph.invoke(
            ApprovalRequest(approved=approved, approver=_approver_user_ref()),
            config=config,
        ),
    )


# --------------------------------------------------------------------------- #
# RED → GREEN: clock injection contract
# --------------------------------------------------------------------------- #


def test_orchestration_audit_timestamps_are_deterministic_with_injected_clock():
    """A frozen clock yields identical timestamps across audit records.

    The 4R review (R3 F2) caught that ``_build_audit_record`` and
    ``WorkbenchService._record_audit`` called ``datetime.now(UTC)``
    directly, which makes audit timestamps non-deterministic and breaks
    replay-based review. The fix threads a ``clock: Callable[[], datetime]``
    parameter through both surfaces; a frozen clock MUST produce
    identical timestamps for every record written in a single graph run.
    """
    workbench, gate, audits = _environment_with_clock(_frozen_clock)
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        clock=_frozen_clock,
    )

    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "frozen-1"}},
        initial=_initial_state(),
        approved=True,
    )

    # Every audit record in a single run shares the frozen clock value.
    iso_timestamps = {record["timestamp"] for record in final["audit_records"]}
    assert iso_timestamps == {_INITIAL_CLOCK.isoformat()}, (
        f"all audit timestamps in a single run must equal the frozen clock; "
        f"got {iso_timestamps}"
    )

    # The underlying AuditRecord also reflects the injected clock.
    persisted = audits.all()
    assert persisted, "graph must write at least one audit record"
    assert {record.timestamp for record in persisted} == {_INITIAL_CLOCK}


def test_orchestration_audit_timestamps_advance_with_injected_clock():
    """Advancing the clock between runs yields strictly increasing timestamps.

    Reviewers rely on audit ordering to reconstruct the timeline of a
    session; the injected clock must surface that ordering instead of
    collapsing every record into the same wall-clock second.
    """
    # Two frozen clocks: the second is offset by 5 minutes.
    second_clock_value = _INITIAL_CLOCK + timedelta(minutes=5)

    def first_clock() -> datetime:
        return _INITIAL_CLOCK

    def second_clock() -> datetime:
        return second_clock_value

    # First run: uses the initial clock.
    workbench, gate, audits = _environment_with_clock(first_clock)
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        clock=first_clock,
    )
    first_run = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": "advance-1"}},
        initial=_initial_state(),
        approved=True,
    )

    # Second run: same workbench / gate / audits, but the clock is advanced.
    graph_2 = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        clock=second_clock,
    )
    second_run = _run_with_approval(
        graph_2,
        config={"configurable": {"thread_id": "advance-2"}},
        initial=_initial_state(),
        approved=True,
    )

    first_timestamps = {record["timestamp"] for record in first_run["audit_records"]}
    second_timestamps = {record["timestamp"] for record in second_run["audit_records"]}
    assert first_timestamps == {_INITIAL_CLOCK.isoformat()}
    assert second_timestamps == {second_clock_value.isoformat()}


def test_workbench_service_record_audit_uses_injected_clock():
    """``WorkbenchService._record_audit`` honors the injected clock.

    The service-level test pins the contract on the second call site
    that the 4R review flagged. ``record_login`` must produce an audit
    record whose ``timestamp`` equals the clock-supplied value.
    """
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        clock=lambda: _INITIAL_CLOCK,
    )

    workbench.record_login(actor_id="user-1", session_id="sess-1")

    persisted = workbench.audits.all()  # type: ignore[attr-defined]
    assert len(persisted) == 1
    assert persisted[0].timestamp == _INITIAL_CLOCK
    assert persisted[0].action == "session.login"


def test_workbench_service_defaults_to_utcnow_when_clock_not_supplied():
    """The clock parameter must default to ``datetime.now(UTC)`` for back-compat.

    The fix is non-breaking: existing callers that do not pass a
    ``clock`` keep getting a real ``datetime.now(UTC)`` value. The
    assertion only checks that the timestamp is timezone-aware (it would
    be naive if the default regressed to ``datetime.utcnow()``), so the
    test is robust to wall-clock drift.
    """
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
    )
    workbench.record_login(actor_id="user-1", session_id="sess-default")

    persisted = workbench.audits.all()  # type: ignore[attr-defined]
    assert len(persisted) == 1
    assert persisted[0].timestamp.tzinfo is not None
    assert persisted[0].timestamp.tzinfo == UTC


@pytest.mark.parametrize(
    "clock_offset_minutes, thread_id",
    [
        (0, "frozen-zero"),
        (1, "frozen-one"),
        (60, "frozen-hour"),
    ],
)
def test_clock_injection_works_across_multiple_instantiations(clock_offset_minutes: int, thread_id: str):
    """Triangulation: three distinct clock offsets all produce deterministic timestamps.

    The parametrized cases cover the common drift patterns a reviewer
    would see (same second, 1 minute, 1 hour) and pin the contract that
    the clock is honored end-to-end across the workbench + graph.
    """
    clock_value = _INITIAL_CLOCK + timedelta(minutes=clock_offset_minutes)
    workbench, gate, audits = _environment_with_clock(lambda: clock_value)
    graph = build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        clock=lambda: clock_value,
    )

    final = _run_with_approval(
        graph,
        config={"configurable": {"thread_id": thread_id}},
        initial=_initial_state(),
        approved=True,
    )

    iso_timestamps = {record["timestamp"] for record in final["audit_records"]}
    assert iso_timestamps == {clock_value.isoformat()}
