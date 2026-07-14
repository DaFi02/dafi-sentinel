import json
from pathlib import Path

import pytest

from dafi_sentinel.ingestion.service import (
    DatasetValidationError,
    InMemoryIncidentStore,
    ingest_incident_dataset,
)
from dafi_sentinel.security.policy import RedactionService


FIXTURES = Path(__file__).parent / "fixtures"


def _jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()]


def test_valid_dataset_ingests_stable_timeline_and_evidence_ids():
    store = InMemoryIncidentStore()

    result = ingest_incident_dataset(
        _jsonl("valid_incident_dataset.jsonl"),
        session_id="session-1",
        store=store,
        redactor=RedactionService(),
    )

    assert [record.evidence_ref.evidence_id for record in result.records] == [
        "ev-inc-001-fixtures-incidents-checkout-jsonl-row-1",
        "ev-inc-001-fixtures-incidents-checkout-jsonl-row-2",
    ]
    assert [record.source.row for record in store.list_records("session-1")] == [1, 2]


def test_malformed_row_reports_structured_error_and_rolls_back_state():
    store = InMemoryIncidentStore()
    ingest_incident_dataset(_jsonl("valid_incident_dataset.jsonl")[:1], "session-1", store, RedactionService())

    with pytest.raises(DatasetValidationError) as failure:
        ingest_incident_dataset(_jsonl("malformed_incident_dataset.jsonl"), "session-2", store, RedactionService())

    assert [(error.row, error.field) for error in failure.value.errors] == [(1, "timestamp")]
    assert store.list_records("session-2") == []
    assert len(store.list_records("session-1")) == 1


def test_source_traceability_and_redaction_handoff_are_preserved():
    result = ingest_incident_dataset(
        _jsonl("valid_incident_dataset.jsonl"),
        session_id="session-1",
        store=InMemoryIncidentStore(),
        redactor=RedactionService(),
    )

    sensitive_record = result.records[1]
    assert sensitive_record.source.uri == "fixtures/incidents/checkout.jsonl"
    assert sensitive_record.source.row == 2
    assert "sk_live_123456" not in sensitive_record.redacted_summary
    assert sensitive_record.fields["api_key"] == "[REDACTED:SECRET:1]"
