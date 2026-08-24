"""Opt-in loader for already-prepared local HDFS_v1 evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dafi_sentinel.api.services import WorkbenchService
from dafi_sentinel.domain.models import Document, SourceMetadata
from dafi_sentinel.ingestion.hdfs_v1 import (
    ALLOWED_LABELS,
    HDFS_V1_CITATIONS,
    LABEL_SEMANTICS,
    LOCAL_HDFS_ROOT,
    LOGHUB_NOTICE,
)
from dafi_sentinel.ingestion.service import InMemoryIncidentStore, ingest_incident_dataset
from dafi_sentinel.retrieval.contracts import InMemoryRetrievalIndex
from dafi_sentinel.security.policy import RedactionService

REQUIRED_PROVENANCE_FIELDS = frozenset(
    {
        "dataset.name",
        "dataset.version",
        "dataset.checksum",
        "dataset.trace_id",
        "dataset.label",
        "dataset.label_semantics",
        "dataset.selection_rule",
        "dataset.attribution.notice",
        "dataset.attribution.citations",
    }
)
HDFS_V1_MANIFEST_PATH = Path(__file__).parents[1] / "ingestion" / "manifests" / "hdfs_v1.json"
HDFS_V1_MANIFEST = json.loads(HDFS_V1_MANIFEST_PATH.read_text(encoding="utf-8"))
EXPECTED_HDFS_V1_SOURCE_URI = HDFS_V1_MANIFEST["source"]["uri"]
EXPECTED_HDFS_V1_VERSION = HDFS_V1_MANIFEST["dataset"]["version"]
EXPECTED_HDFS_V1_CHECKSUM = HDFS_V1_MANIFEST["source"]["checksum"]


def seed_local_hdfs_demo(workbench: WorkbenchService, *, owner_id: str, demo_path: Path) -> None:
    """Seed validated local-only HDFS rows; this function never downloads data."""
    _require_local_path(demo_path)
    if not demo_path.is_file():
        raise RuntimeError(
            "DAFI_HDFS_DEMO_PATH does not point to a prepared local HDFS_v1 JSONL file; "
            "prepare the local-only HDFS_v1 demo first with "
            "uv run python scripts/prepare_hdfs_v1_demo.py --acknowledge-loghub-terms."
        )

    rows = _read_validated_rows(demo_path)
    records = ingest_incident_dataset(rows, "hdfs-v1-local-demo", InMemoryIncidentStore(), RedactionService()).records
    for record in records:
        workbench.evidence.save_evidence(owner_id, record)

    documents = tuple(
        Document(
            id=f"hdfs-v1-{record.evidence_ref.evidence_id}",
            title="LogHub HDFS_v1 operational benchmark evidence",
            body=(
                f"{record.redacted_summary}\n"
                f"Trace ID: {record.fields['dataset.trace_id']}\n"
                f"Benchmark label: {record.fields['dataset.label']}\n"
                f"{LABEL_SEMANTICS}"
            ),
            source=record.source,
            evidence_ids=(record.evidence_ref.evidence_id,),
        )
        for record in records
    )
    workbench.seed_documents((*workbench.documents, *documents))
    workbench.retrieval_index = InMemoryRetrievalIndex(workbench.documents)


def _require_local_path(path: Path) -> None:
    try:
        path.resolve().relative_to(LOCAL_HDFS_ROOT)
    except ValueError as error:
        raise RuntimeError(f"DAFI_HDFS_DEMO_PATH must be below {LOCAL_HDFS_ROOT}") from error


def _read_validated_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"invalid HDFS_v1 JSONL at line {line_number}") from error
        if not isinstance(row, dict):
            raise RuntimeError(f"invalid HDFS_v1 JSONL row at line {line_number}")
        _validate_provenance(row, line_number)
        rows.append(row)
    if not rows:
        raise RuntimeError("prepared HDFS_v1 JSONL contains no evidence rows")
    return rows


def _validate_provenance(row: dict[str, Any], line_number: int) -> None:
    fields = row.get("fields")
    source = row.get("source")
    if not isinstance(fields, dict) or not REQUIRED_PROVENANCE_FIELDS.issubset(fields):
        raise RuntimeError(f"HDFS_v1 row {line_number} is missing required provenance fields")
    if fields["dataset.name"] != "LogHub HDFS_v1":
        raise RuntimeError(f"HDFS_v1 row {line_number} has an invalid dataset name")
    if fields["dataset.version"] != EXPECTED_HDFS_V1_VERSION:
        raise RuntimeError(f"HDFS_v1 row {line_number} has an invalid dataset version")
    if fields["dataset.checksum"] != EXPECTED_HDFS_V1_CHECKSUM:
        raise RuntimeError(f"HDFS_v1 row {line_number} has an invalid dataset checksum")
    if fields["dataset.attribution.notice"] != LOGHUB_NOTICE:
        raise RuntimeError(f"HDFS_v1 row {line_number} has an invalid dataset attribution notice")
    if fields["dataset.attribution.citations"] != list(HDFS_V1_CITATIONS):
        raise RuntimeError(f"HDFS_v1 row {line_number} has invalid dataset attribution citations")
    if fields["dataset.label"] not in ALLOWED_LABELS:
        raise RuntimeError(f"HDFS_v1 row {line_number} has an unsupported benchmark label")
    if fields["dataset.label_semantics"] != LABEL_SEMANTICS:
        raise RuntimeError(f"HDFS_v1 row {line_number} has invalid label semantics")
    if not isinstance(source, dict) or not source.get("uri") or source.get("row") is None:
        raise RuntimeError(f"HDFS_v1 row {line_number} is missing source coordinates")
    if source["uri"] != EXPECTED_HDFS_V1_SOURCE_URI:
        raise RuntimeError(f"HDFS_v1 row {line_number} has an invalid source URI")
