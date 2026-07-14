from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Literal


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


@dataclass(frozen=True)
class Permission:
    name: str


@dataclass(frozen=True)
class Role:
    name: str
    permissions: tuple[Permission, ...] = ()

    def allows(self, permission_name: str) -> bool:
        return any(permission.name == permission_name for permission in self.permissions)


@dataclass(frozen=True)
class ActorRef:
    id: str
    kind: Literal["user", "service", "agent"]


@dataclass(frozen=True)
class UserRef:
    id: str
    display_name: str
    roles: tuple[Role, ...] = ()


@dataclass(frozen=True)
class SourceMetadata:
    uri: str
    row: int | None = None
    offset: int | None = None

    @property
    def stable_part(self) -> str:
        uri_part = _slug(self.uri)
        if self.row is not None:
            return f"{uri_part}-row-{self.row}"
        if self.offset is not None:
            return f"{uri_part}-offset-{self.offset}"
        return uri_part


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source: SourceMetadata


@dataclass(frozen=True)
class RawIncidentRecord:
    incident_id: str
    timestamp: datetime
    source: SourceMetadata
    summary: str
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def evidence_id(self) -> str:
        return f"ev-{_slug(self.incident_id)}-{self.source.stable_part}"


@dataclass(frozen=True)
class RedactedIncidentRecord:
    evidence_ref: EvidenceRef
    timestamp: datetime
    source: SourceMetadata
    redacted_summary: str
    fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: RawIncidentRecord, redacted_summary: str) -> RedactedIncidentRecord:
        return cls(
            evidence_ref=EvidenceRef(raw.evidence_id, raw.source),
            timestamp=raw.timestamp,
            source=raw.source,
            redacted_summary=redacted_summary,
            fields=dict(raw.fields),
        )


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    body: str
    source: SourceMetadata
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    required_permission: Permission | None = None


@dataclass(frozen=True)
class ChartSpec:
    kind: Literal["line", "bar", "scatter", "table"]
    title: str
    x: str
    y: str
    evidence_ids: tuple[str, ...]

    def as_dashboard_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class AuditRecord:
    id: str
    actor: ActorRef
    action: str
    decision: PolicyDecision
    timestamp: datetime
    role_context: tuple[str, ...] = ()
