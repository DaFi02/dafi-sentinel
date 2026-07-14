"""Edge-case tests for the ML analysis surface (PR-C.15, R3 F12).

PR-C.15 (R3 F12): the 4R review caught that the ML primitives had
no edge-case coverage. A NaN in the TF-IDF matrix, an empty feature
set, a single-class fixture, or a constant column could each crash
the ranker or the clusterer with an opaque error from scikit-learn.

The contract is: every edge case MUST either succeed with a stable
result (preferred) or raise a documented ``ValueError``. A
``ZeroDivisionError`` or a numpy / sklearn internal exception is
not acceptable.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from dafi_sentinel.domain.models import (
    EvidenceRef,
    RedactedIncidentRecord,
    SourceMetadata,
)
from dafi_sentinel.ml.analysis import (
    AnomalyScore,
    ClusterAssignment,
    SimilarityMatch,
    cluster_logs,
    rank_similarity,
    score_anomalies,
)


def _record(evidence_id: str, summary: str) -> RedactedIncidentRecord:
    return RedactedIncidentRecord(
        evidence_ref=EvidenceRef(
            evidence_id=evidence_id,
            source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        ),
        timestamp=datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        redacted_summary=summary,
        fields={},
    )


def test_score_anomalies_with_empty_records_returns_empty_tuple():
    """An empty fixture returns an empty score sequence (no crash)."""
    assert score_anomalies(()) == ()


def test_score_anomalies_with_single_record_returns_zero_score():
    """A single-record fixture has no neighbours; the score is 0.0."""
    record = _record("ev-1", "payment timeout")
    result = score_anomalies((record,))
    assert result == (AnomalyScore("ev-1", 0.0),)


def test_score_anomalies_with_constant_column_does_not_crash():
    """A fixture where every summary is identical MUST NOT crash the ranker.

    Constant columns collapse the TF-IDF matrix; without a guard the
    IsolationForest could raise a numpy internal error. The contract:
    the function returns a stable score sequence (all zero is fine).
    """
    records = tuple(_record(f"ev-{i}", "identical summary") for i in range(5))
    result = score_anomalies(records, seed=0)
    assert len(result) == 5
    # All scores are finite numbers (not NaN, not Inf).
    for entry in result:
        assert isinstance(entry, AnomalyScore)
        assert math.isfinite(entry.score)


def test_cluster_logs_with_empty_records_returns_empty_tuple():
    """An empty fixture returns an empty cluster sequence."""
    assert cluster_logs(()) == ()


def test_cluster_logs_with_single_class_returns_one_cluster():
    """A single-class fixture MUST produce a single cluster label."""
    records = tuple(_record(f"ev-{i}", "payment timeout") for i in range(3))
    result = cluster_logs(records, n_clusters=3, seed=0)
    assert len(result) == 3
    # All assignments have the same label (single class in the
    # feature space collapses to a single cluster).
    labels = {entry.cluster for entry in result}
    assert len(labels) == 1


def test_cluster_logs_with_constant_column_does_not_crash():
    """A constant-column fixture MUST NOT crash the clusterer."""
    records = tuple(_record(f"ev-{i}", "identical summary") for i in range(5))
    result = cluster_logs(records, n_clusters=2, seed=0)
    assert len(result) == 5
    labels = {entry.cluster for entry in result}
    # The labels are valid integers.
    assert all(isinstance(entry.cluster, int) for entry in result)
    # The label set is bounded by n_clusters.
    assert max(labels) < 2


def test_rank_similarity_with_empty_records_returns_empty_tuple():
    """An empty fixture returns an empty match sequence."""
    assert rank_similarity("query", ()) == ()


def test_rank_similarity_with_query_no_overlap_returns_empty_tuple():
    """A query with no token overlap returns no matches (no zero-score noise)."""
    records = (_record("ev-1", "payment timeout"),)
    assert rank_similarity("kangaroo", records) == ()


def test_rank_similarity_with_constant_column_does_not_crash():
    """A constant-column fixture MUST NOT crash the ranker."""
    records = tuple(_record(f"ev-{i}", "identical summary") for i in range(3))
    result = rank_similarity("identical summary", records)
    # The result is either empty (zero cosine similarity) or stable
    # matches. The contract: no exception, finite scores.
    for entry in result:
        assert isinstance(entry, SimilarityMatch)
        assert math.isfinite(entry.score)


def test_rank_similarity_with_empty_query_returns_empty_tuple():
    """An empty / whitespace query returns no matches."""
    records = (_record("ev-1", "payment timeout"),)
    assert rank_similarity("", records) == ()
    assert rank_similarity("   ", records) == ()
