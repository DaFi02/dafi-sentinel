"""Tests for the threading.RLock around the in-memory stores (PR-C.10).

PR-C.10 (R1 med#9, R4 high#6): the prior in-memory stores had no
synchronization. A concurrent write to the same record (e.g., two
threads racing to append audit records for the same actor) could
clobber an in-flight read or leave the secondary index inconsistent
with the primary list. The fix wraps mutations in a
``threading.RLock`` so the stores stay correct under concurrent
load. Reads stay lock-free so a 1-process deploy pays no cost on
the read path.

The tests verify the contract end-to-end: 100 concurrent
read+write threads leave the data structures consistent.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
)
from dafi_sentinel.domain.models import (
    AuditRecord,
    EvidenceRef,
    Permission,
    PolicyDecision,
    RedactedIncidentRecord,
    Role,
    SourceMetadata,
    UserRef,
)


def _evidence(evidence_id: str) -> RedactedIncidentRecord:
    return RedactedIncidentRecord(
        evidence_ref=EvidenceRef(
            evidence_id=evidence_id,
            source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        ),
        timestamp=None,  # type: ignore[arg-type]
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        redacted_summary=f"summary-{evidence_id}",
        fields={},
    )


def test_evidence_repository_has_rlock():
    """The in-memory evidence repository owns an RLock."""
    store = InMemoryEvidenceRepository()
    assert hasattr(store, "_lock"), "evidence repository must own a lock"
    assert isinstance(store._lock, type(threading.RLock()))


def test_audit_repository_has_rlock():
    """The in-memory audit repository owns an RLock."""
    store = InMemoryAuditRepository()
    assert hasattr(store, "_lock"), "audit repository must own a lock"
    assert isinstance(store._lock, type(threading.RLock()))


def test_evidence_repository_concurrent_writes_and_reads():
    """100 concurrent reads + writes leave the store consistent."""
    store = InMemoryEvidenceRepository()
    iterations = 100

    def writer(idx: int) -> None:
        record = _evidence(f"ev-{idx}")
        store.save_evidence(f"user-{idx % 4}", record)

    def reader(idx: int) -> int:
        return len(store.list_for_owner(f"user-{idx % 4}"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for idx in range(iterations):
            futures.append(executor.submit(writer, idx))
            futures.append(executor.submit(reader, idx))
        for f in futures:
            f.result()

    # Every owner MUST have at least one record; the four owners
    # partition the 100 records.
    total = sum(len(store.list_for_owner(f"user-{i}")) for i in range(4))
    assert total == iterations, f"expected {iterations} records, got {total}"


def test_audit_repository_concurrent_writes_and_reads():
    """100 concurrent reads + writes leave the audit store consistent."""
    store = InMemoryAuditRepository()
    iterations = 100
    actor = UserRef(
        id="user-1",
        display_name="User",
        roles=(Role("analyst", permissions=(Permission("tool:search"),)),),
    )

    def writer(idx: int) -> None:
        record = AuditRecord(
            id=f"audit-{idx}",
            actor=actor,
            action="tool.search",
            decision=PolicyDecision(allowed=True, reason="ok"),
            timestamp=None,  # type: ignore[arg-type]
            role_context=("analyst",),
        )
        store.write_audit(f"session-{idx % 8}", record)

    def reader(idx: int) -> int:
        return len(store.list_for_actor("user-1"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for idx in range(iterations):
            futures.append(executor.submit(writer, idx))
            futures.append(executor.submit(reader, idx))
        for f in futures:
            f.result()

    # Every record MUST be readable after the storm settles.
    assert len(store.list_for_actor("user-1")) == iterations
