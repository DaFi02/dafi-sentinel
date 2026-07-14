"""Deterministic ML incident analysis.

The PR4 work-unit uses scikit-learn primitives behind a thin, deterministic
adapter. Every public function takes a ``seed`` argument so identical
fixtures produce identical scores, cluster labels, and similarity
rankings. The adapter is the only place that imports scikit-learn so the
domain layer stays free of ML dependencies.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from dafi_sentinel.domain.models import RedactedIncidentRecord


@dataclass(frozen=True)
class AnomalyScore:
    evidence_id: str
    score: float


@dataclass(frozen=True)
class ClusterAssignment:
    evidence_id: str
    cluster: int


@dataclass(frozen=True)
class SimilarityMatch:
    evidence_id: str
    score: float


def _summaries(records: Sequence[RedactedIncidentRecord]) -> list[str]:
    return [record.redacted_summary for record in records]


def _evidence_ids(records: Sequence[RedactedIncidentRecord]) -> list[str]:
    return [record.evidence_ref.evidence_id for record in records]


def _text_features(records: Sequence[RedactedIncidentRecord]):
    vectorizer = TfidfVectorizer()
    return vectorizer, vectorizer.fit_transform(_summaries(records))


def score_anomalies(
    records: Sequence[RedactedIncidentRecord],
    *,
    seed: int = 0,
    contamination: float = 0.1,
) -> tuple[AnomalyScore, ...]:
    """Score every record with a seeded IsolationForest.

    Higher scores indicate more anomalous behaviour. The score sequence
    is stable for the same fixture and ``seed`` because
    ``IsolationForest`` is initialised with ``random_state=seed``.
    """
    if not records:
        return ()

    evidence_ids = _evidence_ids(records)
    _, features = _text_features(records)

    if features.shape[0] < 2:
        return tuple(AnomalyScore(evidence_id, 0.0) for evidence_id in evidence_ids)

    model = IsolationForest(contamination=contamination, random_state=seed)
    model.fit(features)
    # ``decision_function`` is higher for normal points; negate so positive means anomalous.
    raw_scores = -model.decision_function(features)

    return tuple(
        AnomalyScore(evidence_id, float(score))
        for evidence_id, score in zip(evidence_ids, raw_scores)
    )


def cluster_logs(
    records: Sequence[RedactedIncidentRecord],
    *,
    n_clusters: int = 2,
    seed: int = 0,
) -> tuple[ClusterAssignment, ...]:
    """Cluster redacted summaries with a seeded KMeans.

    Cluster labels are integers in ``range(n_clusters)``. The result is
    stable for the same fixture and ``seed`` because ``KMeans`` is
    initialised with ``random_state=seed`` and ``n_init=10``.
    """
    if not records:
        return ()

    evidence_ids = _evidence_ids(records)
    _, features = _text_features(records)

    bounded_clusters = max(1, min(n_clusters, features.shape[0]))
    model = KMeans(n_clusters=bounded_clusters, random_state=seed, n_init=10)
    labels = model.fit_predict(features)

    return tuple(
        ClusterAssignment(evidence_id, int(label))
        for evidence_id, label in zip(evidence_ids, labels)
    )


def rank_similarity(
    query: str,
    records: Sequence[RedactedIncidentRecord],
    *,
    seed: int = 0,  # accepted for API symmetry; TF-IDF is deterministic regardless.
) -> tuple[SimilarityMatch, ...]:
    """Rank records by cosine similarity to ``query``.

    Results are returned in descending score order, tied by evidence ID
    for a fully deterministic order. Zero-score matches (queries with no
    overlapping tokens) are dropped so callers never see fake matches.
    """
    if not records or not query.strip():
        return ()

    evidence_ids = _evidence_ids(records)
    vectorizer, record_features = _text_features(records)
    query_features = vectorizer.transform([query])

    similarities = cosine_similarity(query_features, record_features).flatten()

    pairs = sorted(
        (
            (evidence_id, float(score))
            for evidence_id, score in zip(evidence_ids, similarities)
            if score > 0.0
        ),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return tuple(SimilarityMatch(evidence_id, score) for evidence_id, score in pairs)
