from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from dafi_sentinel.domain.models import EvidenceRef, RawIncidentRecord, RedactedIncidentRecord, SourceMetadata


class Redactor(Protocol):
    def redact_text(self, value: str) -> str: ...
    def redact_value(self, value: object) -> object: ...


@dataclass(frozen=True)
class ValidationError:
    row: int
    field: str
    message: str


class DatasetValidationError(ValueError):
    def __init__(self, errors: tuple[ValidationError, ...]) -> None:
        self.errors = errors
        super().__init__("incident dataset validation failed")


@dataclass(frozen=True)
class IngestionResult:
    records: tuple[RedactedIncidentRecord, ...]


@dataclass
class InMemoryIncidentStore:
    _records: dict[str, list[RedactedIncidentRecord]] = field(default_factory=dict)

    def commit(self, session_id: str, records: tuple[RedactedIncidentRecord, ...]) -> None:
        self._records.setdefault(session_id, []).extend(records)

    def list_records(self, session_id: str) -> list[RedactedIncidentRecord]:
        return list(self._records.get(session_id, []))


def ingest_incident_dataset(
    rows: list[dict[str, Any]],
    session_id: str,
    store: InMemoryIncidentStore,
    redactor: Redactor,
) -> IngestionResult:
    raw_records = _validate(rows)
    redacted_records = tuple(
        RedactedIncidentRecord(
            evidence_ref=EvidenceRef(raw.evidence_id, raw.source),
            timestamp=raw.timestamp,
            source=raw.source,
            redacted_summary=redactor.redact_text(raw.summary),
            fields=redactor.redact_value(raw.fields),
        )
        for raw in sorted(raw_records, key=lambda record: (record.timestamp, record.evidence_id))
    )
    store.commit(session_id, redacted_records)
    return IngestionResult(redacted_records)


def _validate(rows: list[dict[str, Any]]) -> tuple[RawIncidentRecord, ...]:
    errors: list[ValidationError] = []
    records: list[RawIncidentRecord] = []

    for index, row in enumerate(rows, start=1):
        source_payload = row.get("source") if isinstance(row.get("source"), dict) else {}
        row_number = source_payload.get("row", index)
        for field_name in ("incident_id", "timestamp", "source", "summary"):
            if not row.get(field_name):
                errors.append(ValidationError(row_number, field_name, f"missing required field {field_name}"))

        if errors:
            continue

        try:
            timestamp = datetime.fromisoformat(str(row["timestamp"]))
        except ValueError:
            errors.append(ValidationError(row_number, "timestamp", "timestamp must be ISO-8601"))
            continue

        records.append(
            RawIncidentRecord(
                incident_id=str(row["incident_id"]),
                timestamp=timestamp,
                source=SourceMetadata(
                    uri=str(source_payload["uri"]),
                    row=source_payload.get("row"),
                    offset=source_payload.get("offset"),
                ),
                summary=str(row["summary"]),
                fields=dict(row.get("fields", {})),
            )
        )

    if errors:
        raise DatasetValidationError(tuple(errors))
    return tuple(records)
