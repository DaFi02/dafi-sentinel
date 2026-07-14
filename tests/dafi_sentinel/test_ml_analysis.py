"""Tests for the deterministic ML incident analysis.

The ML analysis layer is part of the PR4 work-unit and must produce stable
anomaly scores, cluster assignments, and similarity rankings when called
with the same fixture and seed. These tests assert the deterministic
contract from the ML incident analysis specification.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dafi_sentinel.domain.models import (
    RawIncidentRecord,
    RedactedIncidentRecord,
    SourceMetadata,
)
from dafi_sentinel.ml import analysis


FIXTURES = Path(__file__).parent / "fixtures"


def _load_records(name: str) -> tuple[RedactedIncidentRecord, ...]:
    rows = [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()]
    records: list[RedactedIncidentRecord] = []
    for row in rows:
        source_payload = row["source"]
        source = SourceMetadata(
            uri=source_payload["uri"],
            row=source_payload.get("row"),
            offset=source_payload.get("offset"),
        )
        raw = RawIncidentRecord(
            incident_id=row["incident_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            source=source,
            summary=row["summary"],
            fields=row.get("fields", {}),
        )
        records.append(RedactedIncidentRecord.from_raw(raw, redacted_summary=row["summary"]))
    return tuple(records)


def test_score_anomalies_is_deterministic_across_two_runs_with_same_seed():
    """Same fixture + same seed must produce identical anomaly score sequences."""
    records = _load_records("ml_incident_dataset.jsonl")

    first = analysis.score_anomalies(records, seed=42)
    second = analysis.score_anomalies(records, seed=42)

    assert [item.evidence_id for item in first] == [item.evidence_id for item in second]
    assert [item.score for item in first] == [item.score for item in second]
    # Scores must be finite floats and ranking must reference known evidence IDs.
    assert all(isinstance(item.score, float) for item in first)
    known_ids = {record.evidence_ref.evidence_id for record in records}
    assert {item.evidence_id for item in first} == known_ids


def test_cluster_logs_is_deterministic_and_labels_align_with_records():
    """Same fixture + same seed must yield identical cluster labels per evidence ID."""
    records = _load_records("ml_incident_dataset.jsonl")

    first = analysis.cluster_logs(records, n_clusters=2, seed=7)
    second = analysis.cluster_logs(records, n_clusters=2, seed=7)

    assert [(item.evidence_id, item.cluster) for item in first] == [
        (item.evidence_id, item.cluster) for item in second
    ]
    assert {item.cluster for item in first} <= {0, 1}
    assert len(first) == len(records)


def test_rank_similarity_returns_deterministic_relevance_order_with_scores():
    """Ranking by cosine similarity to the query must be deterministic and cite evidence IDs."""
    records = _load_records("ml_incident_dataset.jsonl")
    query = "checkout latency payment timeout"

    first = analysis.rank_similarity(query, records, seed=0)
    second = analysis.rank_similarity(query, records, seed=0)

    assert [item.evidence_id for item in first] == [item.evidence_id for item in second]
    assert [item.score for item in first] == [item.score for item in second]
    # Scores must be monotonically non-increasing (highest relevance first).
    scores = [item.score for item in first]
    assert scores == sorted(scores, reverse=True)
    # Every match must reference a known evidence ID and a finite score.
    known_ids = {record.evidence_ref.evidence_id for record in records}
    assert {item.evidence_id for item in first} <= known_ids
    assert all(0.0 <= item.score <= 1.0 for item in first)


def test_score_anomalies_handles_empty_record_set_without_crashing():
    """Empty input must return an empty anomaly sequence (no exceptions, no fake rows)."""
    result = analysis.score_anomalies([], seed=0)
    assert result == ()


def test_rank_similarity_handles_query_with_no_matching_tokens():
    """When the query has no overlap with any record, the result must be empty (no fake matches)."""
    records = _load_records("ml_incident_dataset.jsonl")
    result = analysis.rank_similarity("zzzqqqxxx", records, seed=0)
    assert result == ()


def test_committed_fixture_guards_regression_in_scores_clusters_and_ranking():
    """Pinned expected output for the small guard fixture.

    This is the "Fixture guards regression" scenario from the spec:
    deviations in scores, cluster labels, or similarity ranking fail
    the build. Values were captured on the deterministic PR4 pipeline
    and must be updated only with intent, never silently.
    """
    records = _load_records("ml_guard_fixture.jsonl")

    anomalies = analysis.score_anomalies(records, seed=0)
    clusters = analysis.cluster_logs(records, n_clusters=2, seed=0)
    checkout_matches = analysis.rank_similarity("checkout latency", records, seed=0)
    database_matches = analysis.rank_similarity("database", records, seed=0)

    assert [round(item.score, 10) for item in anomalies] == [
        -0.1968026505,
        0.0492006626,
        -0.1968026505,
    ]
    assert [(item.evidence_id, item.cluster) for item in clusters] == [
        ("ev-ml-guard-001-fixtures-incidents-ml-guard-jsonl-row-1", 1),
        ("ev-ml-guard-001-fixtures-incidents-ml-guard-jsonl-row-2", 0),
        ("ev-ml-guard-001-fixtures-incidents-ml-guard-jsonl-row-3", 1),
    ]
    assert [(item.evidence_id, round(item.score, 10)) for item in checkout_matches] == [
        ("ev-ml-guard-001-fixtures-incidents-ml-guard-jsonl-row-1", 0.7071067812),
        ("ev-ml-guard-001-fixtures-incidents-ml-guard-jsonl-row-3", 0.7071067812),
    ]
    assert [(item.evidence_id, round(item.score, 10)) for item in database_matches] == [
        ("ev-ml-guard-001-fixtures-incidents-ml-guard-jsonl-row-2", 0.5),
    ]
