"""Tests for the in-memory audit repository (R2 crit#7 + B.4 runtime checkable).

The 4R review caught that :class:`InMemoryAuditRepository.write_audit`
ignored the ``session_id`` parameter and only indexed records by
``actor_id``. Two different sessions for the same actor ended up
interleaved in the audit log with no way to partition them per session.
The fix:

* Index records by ``(actor_id, session_id)`` so the API can serve a
  per-session slice cheaply.
* ``list_for_actor`` keeps returning the full chronological trace for
  the actor (cross-session), so the existing ``GET /audits`` endpoint
  is unchanged.

B.4: the storage Protocol decorators get ``@runtime_checkable`` so the
:func:`isinstance` guard on the workbench service can fail fast on a
misconfigured adapter. This test pins the contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.domain.models import ActorRef, AuditRecord, PolicyDecision
from dafi_sentinel.storage.contracts import AuditRepository, EvidenceRepository


def _audit_record(*, record_id: str, actor_id: str, action: str) -> AuditRecord:
    return AuditRecord(
        id=record_id,
        actor=ActorRef(id=actor_id, kind="user"),
        action=action,
        decision=PolicyDecision(allowed=True, reason="ok"),
        timestamp=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
    )


# --------------------------------------------------------------------------- #
# B.3 — session_id partitioning
# --------------------------------------------------------------------------- #


def test_audit_repository_partitions_records_by_actor_and_session():
    """The repository must index records by (actor_id, session_id).

    R2 crit#7: prior implementation dropped the ``session_id`` on the
    floor. The fix keys the per-session index by the tuple so a
    reviewer can pull a single session's audit slice without scanning
    every record for the actor.
    """
    repo = InMemoryAuditRepository()
    repo.write_audit("sess-a", _audit_record(record_id="a1", actor_id="user-1", action="session.login"))
    repo.write_audit("sess-a", _audit_record(record_id="a2", actor_id="user-1", action="qa.answer"))
    repo.write_audit("sess-b", _audit_record(record_id="b1", actor_id="user-1", action="session.logout"))

    assert tuple(record.id for record in repo.list_for_session("user-1", "sess-a")) == ("a1", "a2")
    assert tuple(record.id for record in repo.list_for_session("user-1", "sess-b")) == ("b1",)
    # Cross-session slice is still available for the actor.
    assert tuple(record.id for record in repo.list_for_actor("user-1")) == ("a1", "a2", "b1")


def test_audit_repository_list_for_session_returns_empty_for_unknown_session():
    """Unknown (actor, session) tuples return an empty slice, not an error."""
    repo = InMemoryAuditRepository()
    repo.write_audit("sess-a", _audit_record(record_id="a1", actor_id="user-1", action="session.login"))

    assert repo.list_for_session("user-1", "sess-unknown") == ()
    assert repo.list_for_session("user-unknown", "sess-a") == ()


# --------------------------------------------------------------------------- #
# B.4 — runtime_checkable Protocol decoration
# --------------------------------------------------------------------------- #


def test_in_memory_evidence_repository_passes_runtime_checkable_guard():
    """``InMemoryEvidenceRepository`` is an instance of the runtime-checkable Protocol.

    R2 med (asymmetry fix): before the @runtime_checkable decorator
    was added, ``isinstance(adapter, EvidenceRepository)`` raised
    ``TypeError: Instance and class checks can only be used with
    @runtime_checkable protocols``. The decorator plus the widened
    Protocol lets the workbench service guard construction with a
    clean ``isinstance`` call.
    """
    assert isinstance(InMemoryEvidenceRepository(), EvidenceRepository)


def test_in_memory_audit_repository_passes_runtime_checkable_guard():
    """``InMemoryAuditRepository`` is an instance of the runtime-checkable Protocol."""
    assert isinstance(InMemoryAuditRepository(), AuditRepository)


def test_workbench_service_rejects_non_evidence_repository():
    """A misconfigured evidence adapter fails the ``isinstance`` guard fast.

    The guard is a small piece of belt-and-braces defense: even when
    a future caller passes the wrong adapter, the workbench service
    refuses construction instead of crashing on the first request.
    """
    with pytest.raises(TypeError, match="EvidenceRepository"):

        class NotARepository:
            def save_evidence(self, owner_id, record):  # pragma: no cover - partial surface
                return record.evidence_ref

        WorkbenchService(
            evidence=NotARepository(),  # type: ignore[arg-type]
            audits=InMemoryAuditRepository(),
        )


def test_workbench_service_accepts_in_memory_adapters():
    """The default adapters still construct cleanly after the guard.

    Regression: the new ``isinstance`` guard must not regress the
    default_factory path; the in-memory adapters remain the canonical
    in-process implementation.
    """
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
    )
    assert isinstance(workbench.evidence, EvidenceRepository)
    assert isinstance(workbench.audits, AuditRepository)
