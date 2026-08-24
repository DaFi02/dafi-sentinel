from __future__ import annotations

from pathlib import Path

import pytest

from dafi_sentinel.ingestion.hdfs_v1 import build_normalized_rows, select_traces
from dafi_sentinel.ingestion.service import InMemoryIncidentStore, ingest_incident_dataset
from dafi_sentinel.ml.analysis import score_anomalies
from dafi_sentinel.security.policy import RedactionService


ROOT = Path(__file__).parents[2]


def _synthetic_hdfs_rows() -> list[dict[str, object]]:
    traces = {
        "blk_2": ("Normal", ((2, "normal namenode operation"),)),
        "blk_1": ("Anomaly", ((1, "benchmark block processing anomaly"),)),
    }
    return build_normalized_rows(
        select_traces(traces, per_label=1),
        source_uri="https://zenodo.org/api/records/8196385/files/HDFS_v1.zip/content",
        source_version="10.5281/zenodo.8196385",
        source_checksum="md5:76a24b4d9a6164d543fb275f89773260",
        selection_rule="first 1 trace per label after label and trace ID sorting",
    )


def _ingest_synthetic_hdfs_fixture():
    return ingest_incident_dataset(
        _synthetic_hdfs_rows(),
        "hdfs-release-proof",
        InMemoryIncidentStore(),
        RedactionService(),
    ).records


def test_synthetic_hdfs_fixture_has_stable_evidence_ids_and_anomaly_inputs_across_two_runs():
    first_records = _ingest_synthetic_hdfs_fixture()
    second_records = _ingest_synthetic_hdfs_fixture()

    first_scores = score_anomalies(first_records, seed=42)
    second_scores = score_anomalies(second_records, seed=42)

    assert [record.evidence_ref.evidence_id for record in first_records] == [
        record.evidence_ref.evidence_id for record in second_records
    ]
    assert [(score.evidence_id, score.score) for score in first_scores] == [
        (score.evidence_id, score.score) for score in second_scores
    ]
    assert {score.evidence_id for score in first_scores} == {
        record.evidence_ref.evidence_id for record in first_records
    }


def test_hdfs_demo_docs_describe_the_enforced_local_only_provenance_contract():
    readme_path = ROOT / "README.md"
    portfolio_path = ROOT / "PORTFOLIO.md"
    if not readme_path.exists() and not portfolio_path.exists():
        # Root documents are not part of the image build context; this is
        # a full-checkout contract (same co-absence pattern as the pr1
        # inventory guard).
        pytest.skip("root documents absent (containerized run without build context)")

    readme = readme_path.read_text(encoding="utf-8")
    portfolio = portfolio_path.read_text(encoding="utf-8")

    for document in (readme, portfolio):
        assert "https://zenodo.org/api/records/8196385/files/HDFS_v1.zip/content" in document
        assert "md5:76a24b4d9a6164d543fb275f89773260" in document
        assert "No official SHA-256" in document
        assert "not cybersecurity attack conclusions" in document
        assert "not committed or redistributed" in document

    assert "--acknowledge-loghub-terms" in readme
    assert "DAFI_HDFS_DEMO_PATH" in readme
    assert "/evidence/{id}" in readme
    assert "10 traces per label" in portfolio
    assert "Anomaly` then `Normal`" in portfolio
    assert "not statistically representative" in portfolio
