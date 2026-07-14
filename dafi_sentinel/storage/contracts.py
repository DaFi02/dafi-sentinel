from __future__ import annotations

from typing import Protocol, runtime_checkable

from dafi_sentinel.domain.models import AuditRecord, EvidenceRef, RedactedIncidentRecord, UserRef


@runtime_checkable
class EvidenceRepository(Protocol):
    def save_evidence(self, owner_id: str, record: RedactedIncidentRecord) -> EvidenceRef: ...
    def get_evidence(self, evidence_id: str) -> RedactedIncidentRecord | None: ...
    def owner_of(self, evidence_id: str) -> str | None: ...
    def list_for_owner(self, owner_id: str) -> tuple[RedactedIncidentRecord, ...]: ...


class TimelineRepository(Protocol):
    def append_record(self, session_id: str, record: RedactedIncidentRecord) -> None: ...
    def list_records(self, session_id: str) -> list[RedactedIncidentRecord]: ...


@runtime_checkable
class AuditRepository(Protocol):
    def write_audit(self, session_id: str, record: AuditRecord) -> None: ...


@runtime_checkable
class ActorStore(Protocol):
    """Server-side lookup the orchestrator uses to resolve an approver id.

    PR-C.6 (R1 high#2): the prior implementation trusted the
    ``UserRef`` the caller supplied at the approval pause. A
    caller-supplied ``UserRef`` is not authoritative: an attacker can
    forge an id and a permission set in a single payload. The fix
    routes every approval through this protocol so the orchestrator
    can look up the canonical ``UserRef`` for the supplied id and
    apply the store-returned roles/permissions, never the
    caller-supplied ones.

    A ``None`` return signals "unknown id"; the approval node records
    the rejection with ``approval-self-or-unauthorized`` and the
    chart render is skipped.
    """

    def get_user(self, user_id: str) -> UserRef | None: ...
