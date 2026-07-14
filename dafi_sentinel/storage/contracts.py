from __future__ import annotations

from typing import Protocol

from dafi_sentinel.domain.models import AuditRecord, EvidenceRef, RedactedIncidentRecord


class EvidenceRepository(Protocol):
    def save_evidence(self, record: RedactedIncidentRecord) -> EvidenceRef: ...
    def get_evidence(self, evidence_id: str) -> RedactedIncidentRecord | None: ...


class TimelineRepository(Protocol):
    def append_record(self, session_id: str, record: RedactedIncidentRecord) -> None: ...
    def list_records(self, session_id: str) -> list[RedactedIncidentRecord]: ...


class AuditRepository(Protocol):
    def write_audit(self, session_id: str, record: AuditRecord) -> None: ...
