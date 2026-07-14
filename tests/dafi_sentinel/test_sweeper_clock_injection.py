"""Tests for the sweeper clock-injection contract (R3 F6).

The 4R review caught that ``sweep_stale_pauses`` compares a wall-clock
"now" against the checkpointer's ``created_at`` timestamp, so the
test suite had to use ``time.sleep`` to make a freshly-paused
checkpoint appear stale. ``time.sleep`` is flaky in CI: on a busy
runner a 10ms sleep can complete before the checkpoint timestamp is
captured, or the TTL can drift across the sleep boundary. The fix
threads a ``clock`` parameter through the sweeper so the test can
move "now" forward deterministically.

This module pins the contract:

* The sweeper uses the injected ``clock`` for the "now" comparison.
* A clock that returns a time well past the checkpoint's
  ``created_at`` causes the thread to be swept.
* The default ``clock`` is still ``datetime.now(UTC)`` for back-compat.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from dafi_sentinel.orchestration.graph import build_investigation_graph, sweep_stale_pauses
from dafi_sentinel.security.policy import AuditSink, RedactionService, SecurityGate


_INITIAL_CLOCK = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)


def _environment() -> tuple[WorkbenchService, SecurityGate, InMemoryAuditRepository]:
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
        timestamp=_INITIAL_CLOCK.replace(hour=12),
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        redacted_summary="Payment timeout crossed alert threshold",
        fields={"severity": "critical"},
    )
    workbench.evidence.save_evidence("user-1", record)
    gate = SecurityGate(
        redactor=RedactionService(),
        audits=AuditSink(clock=lambda: _INITIAL_CLOCK),
    )
    return workbench, gate, workbench.audits  # type: ignore[return-value]


def _initial_state() -> dict:
    return {
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


def test_sweep_stale_pauses_uses_injected_clock_without_time_sleep():
    """The sweeper's "now" must come from the injected clock.

    R3 F6: the prior test had to use ``time.sleep(0.01)`` to make a
    freshly-paused checkpoint appear stale. A deterministic clock that
    returns a time well past the snapshot's ``created_at`` replaces
    the real-time sleep, so the test is robust against slow CI runners.

    The snapshot's ``created_at`` is set by the InMemorySaver at pause
    time (wall clock); the test clock starts from ``datetime.now(UTC)``
    and advances it by an hour so the age is large enough to clear any
    TTL.
    """
    workbench, gate, audits = _environment()
    graph = build_investigation_graph(workbench=workbench, gate=gate, audits=audits)

    config = {"configurable": {"thread_id": "injected-clock-1"}}
    paused = graph.invoke(_initial_state(), config=config)
    assert "__interrupt__" in paused
    assert graph.get_state(config) is not None

    # The snapshot's created_at is the real wall clock at pause time.
    # Advance the test clock an hour past "now" so the comparison
    # reports an age of ~1h, comfortably above the 0-second TTL.
    future_now = datetime.now(UTC) + timedelta(hours=1)
    swept = sweep_stale_pauses(
        graph,
        thread_ids=["injected-clock-1"],
        ttl_seconds=0,
        clock=lambda: future_now,
    )
    assert swept == 1, f"sweeper should sweep the stale thread; got {swept}"

    snapshot = graph.get_state(config)
    assert snapshot is not None
    assert snapshot.values.get("chart_png") is None
    assert snapshot.values.get("decision_reason") == "approval-timeout"


def test_sweep_stale_pauses_keeps_thread_with_clock_at_creation_time():
    """A clock equal to the wall clock must NOT sweep the thread.

    Pins the contract that a sweeper invoked immediately after the
    pause (no clock offset) does not finalize a freshly paused
    thread. The 1-hour TTL covers any microsecond drift between
    the pause and the sweep.
    """
    workbench, gate, audits = _environment()
    graph = build_investigation_graph(workbench=workbench, gate=gate, audits=audits)

    config = {"configurable": {"thread_id": "injected-clock-2"}}
    paused = graph.invoke(_initial_state(), config=config)
    assert "__interrupt__" in paused

    # The clock is at the wall clock, well within a 1-hour TTL.
    swept = sweep_stale_pauses(
        graph,
        thread_ids=["injected-clock-2"],
        ttl_seconds=3600,
        clock=lambda: datetime.now(UTC),
    )
    assert swept == 0, "fresh thread must not be swept when clock equals wall clock"
