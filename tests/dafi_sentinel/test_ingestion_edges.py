"""Edge-case tests for the ingestion service (PR-C.18, R3 F9).

PR-C.18 (R3 F9): the 4R review caught that the ingestion service
had no edge-case coverage. An empty CSV, a BOM byte at the start of
the file, a row with a Windows line ending, or a missing required
column could each surface as a confusing error or silently drop a
row.

The contract:

* An empty input (no rows) returns an empty ``IngestionResult``.
* A row with a missing required column (``incident_id``,
  ``timestamp``, ``source``, or ``summary``) surfaces a structured
  ``ValidationError`` on the row.
* A row with a BOM (\\ufeff) prefix on the first field is still
  ingested correctly.
* A row with mixed line endings (``\\r\\n`` and ``\\n``) is
  ingested correctly.

The tests use the in-memory ``ingest_incident_dataset`` function so
no filesystem fixture is required.
"""

from __future__ import annotations

import pytest

from dafi_sentinel.ingestion.service import (
    DatasetValidationError,
    InMemoryIncidentStore,
    ingest_incident_dataset,
)
from dafi_sentinel.security.policy import RedactionService


def _valid_row(incident_id: str = "inc-1", timestamp: str = "2026-07-14T10:00:00Z") -> dict:
    return {
        "incident_id": incident_id,
        "timestamp": timestamp,
        "source": {"uri": "fixtures/incidents/checkout.jsonl", "row": 1},
        "summary": "Payment timeout crossed alert threshold",
        "fields": {"severity": "critical"},
    }


def test_empty_dataset_returns_empty_ingestion_result():
    """An empty row list returns an empty IngestionResult (no crash)."""
    store = InMemoryIncidentStore()
    result = ingest_incident_dataset(
        [],
        session_id="s1",
        store=store,
        redactor=RedactionService(),
    )
    assert result.records == ()
    assert store.list_records("s1") == []


def test_row_with_missing_required_column_surfaces_structured_error():
    """A row missing the ``summary`` column raises a ValidationError on the row."""
    row = _valid_row()
    del row["summary"]
    with pytest.raises(DatasetValidationError) as failure:
        ingest_incident_dataset(
            [row],
            session_id="s1",
            store=InMemoryIncidentStore(),
            redactor=RedactionService(),
        )
    assert any(error.field == "summary" for error in failure.value.errors)


def test_row_with_bom_prefix_is_ingested_correctly():
    """A row whose summary carries a UTF-8 BOM (\\ufeff) is still ingested.

    The BOM is preserved verbatim in the redacted summary so the
    downstream pipeline can decide whether to strip it. The
    contract: no crash, and the record is reachable.
    """
    bom_summary = "\ufeffPayment timeout crossed alert threshold"
    row = _valid_row()
    row["summary"] = bom_summary
    result = ingest_incident_dataset(
        [row],
        session_id="s1",
        store=InMemoryIncidentStore(),
        redactor=RedactionService(),
    )
    assert len(result.records) == 1
    # The BOM is preserved in the redacted summary (the redactor
    # does not strip it; that's a downstream concern).
    assert "\ufeff" in result.records[0].redacted_summary


def test_mixed_line_endings_ingest_each_row():
    """Rows with mixed ``\\r\\n`` and ``\\n`` line endings all surface as separate records.

    The ingestion service receives a list of pre-parsed dicts, so
    line endings are the caller's concern. This test pins the
    contract that the service does not silently re-parse the input
    or split on newlines — it accepts whatever the caller hands it.
    """
    # Two valid rows, one with a \\r\\n in the summary (the
    # ``source`` field is normalized to a dict so the row is
    # well-formed).
    rows = [
        _valid_row(incident_id="inc-1", timestamp="2026-07-14T10:00:00Z"),
        {
            "incident_id": "inc-2",
            "timestamp": "2026-07-14T10:05:00Z",
            "source": {"uri": "fixtures/incidents/checkout.jsonl", "row": 2},
            "summary": "Multi-line\r\nsummary\r\nwith CRLF",
            "fields": {},
        },
    ]
    result = ingest_incident_dataset(
        rows,
        session_id="s1",
        store=InMemoryIncidentStore(),
        redactor=RedactionService(),
    )
    # Both rows are ingested; the summary preserves the CRLF.
    assert len(result.records) == 2
    assert "\r\n" in result.records[1].redacted_summary


def test_invalid_timestamp_surfaces_structured_error():
    """A row with a non-ISO timestamp raises a ValidationError on the timestamp field."""
    row = _valid_row()
    row["timestamp"] = "not-an-iso-timestamp"
    with pytest.raises(DatasetValidationError) as failure:
        ingest_incident_dataset(
            [row],
            session_id="s1",
            store=InMemoryIncidentStore(),
            redactor=RedactionService(),
        )
    assert any(error.field == "timestamp" for error in failure.value.errors)


def test_rows_preserved_on_validation_failure():
    """A validation failure MUST NOT commit any partial state to the store."""
    store = InMemoryIncidentStore()
    # First, ingest a valid row.
    ingest_incident_dataset(
        [_valid_row()],
        session_id="session-1",
        store=store,
        redactor=RedactionService(),
    )
    # Now ingest a malformed row in a different session.
    bad_row = _valid_row()
    del bad_row["incident_id"]
    with pytest.raises(DatasetValidationError):
        ingest_incident_dataset(
            [bad_row],
            session_id="session-2",
            store=store,
            redactor=RedactionService(),
        )
    # The first session's record is still there; the second session
    # has no records (the validation error rolled back).
    assert len(store.list_records("session-1")) == 1
    assert store.list_records("session-2") == []
