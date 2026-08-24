"""Local-only preparation for the LogHub HDFS_v1 operational benchmark."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

ALLOWED_LABELS = frozenset({"Normal", "Anomaly"})
LABEL_SEMANTICS = "Operational benchmark metadata; not a cybersecurity attack conclusion."
LOCAL_HDFS_ROOT = Path(".local/hdfs-v1").resolve()
LOGHUB_NOTICE = (
    "The datasets are freely available for research or academic work, subject to the following condition: "
    "For any usage or distribution of the loghub datasets, please refer to the loghub repository URL "
    "(https://github.com/logpai/loghub) and cite the following loghub paper where applicable.\n\n"
    "Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. Loghub: A Large Collection "
    "of System Log Datasets for AI-driven Log Analytics. In ISSRE, 2023.\n\n"
    "The above license notice shall be included in all copies of the datasets."
)
HDFS_V1_CITATIONS = (
    "Wei Xu, Ling Huang, Armando Fox, David Patterson, Michael Jordan. *Detecting Large-Scale "
    "System Problems by Mining Console Logs*. SOSP, 2009.",
    "Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. *Loghub: A Large Collection "
    "of System Log Datasets for AI-driven Log Analytics*. ISSRE, 2023.",
)


class TermsNotAcknowledgedError(PermissionError):
    """Raised before any source I/O when terms acknowledgement is absent."""


Trace = tuple[str, tuple[tuple[int, str], ...]]


def select_traces(traces: dict[str, Trace], per_label: int) -> tuple[tuple[str, Trace], ...]:
    """Return a stable, bounded trace selection ordered by label then trace ID."""
    if per_label < 1:
        raise ValueError("per_label must be at least 1")

    for trace_id, (label, coordinates) in traces.items():
        if not trace_id or trace_id != trace_id.strip():
            raise ValueError("invalid trace identifier")
        if label not in ALLOWED_LABELS:
            raise ValueError(f"unsupported label: {label}")
        if not coordinates:
            raise ValueError(f"missing source coordinates for trace: {trace_id}")

    selected: list[tuple[str, Trace]] = []
    for label in sorted(ALLOWED_LABELS):
        labelled = [(trace_id, trace) for trace_id, trace in traces.items() if trace[0] == label]
        selected.extend(sorted(labelled, key=lambda item: item[0])[:per_label])
    return tuple(selected)


def build_normalized_rows(
    selected: Iterable[tuple[str, Trace]],
    *,
    source_uri: str,
    source_version: str,
    source_checksum: str,
    selection_rule: str,
) -> list[dict[str, object]]:
    """Map selected traces to deterministic, provenance-preserving ingestion rows."""
    rows: list[dict[str, object]] = []
    for order, (trace_id, (label, coordinates)) in enumerate(selected, start=1):
        source_row, summary = coordinates[0]
        rows.append(
            {
                "incident_id": f"hdfs-v1-{trace_id}",
                "timestamp": f"2000-01-01T00:00:{order:02d}+00:00",
                "source": {"uri": source_uri, "row": source_row},
                "summary": summary,
                "fields": {
                    "dataset.name": "LogHub HDFS_v1",
                    "dataset.version": source_version,
                    "dataset.checksum": source_checksum,
                    "dataset.trace_id": trace_id,
                    "dataset.label": label,
                    "dataset.label_semantics": LABEL_SEMANTICS,
                    "dataset.selection_rule": selection_rule,
                    "dataset.timestamp_semantics": "Synthetic deterministic order; HDFS_v1 does not provide incident timestamps.",
                    "dataset.attribution.notice": LOGHUB_NOTICE,
                    "dataset.attribution.citations": list(HDFS_V1_CITATIONS),
                },
            }
        )
    if not rows:
        raise ValueError("selection produced no traces")
    return rows


def prepare_local_demo(
    manifest_path: Path,
    cache_path: Path,
    output_path: Path,
    acknowledged: bool,
    downloader: Callable[[str, Path], None],
) -> None:
    """Prepare ignored output; callers must explicitly acknowledge LogHub terms."""
    if not acknowledged:
        raise TermsNotAcknowledgedError("pass --acknowledge-loghub-terms before downloading or preparing HDFS_v1")
    _require_local_hdfs_path(cache_path)
    _require_local_hdfs_path(output_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["source"]
    if not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        downloader(source["uri"], cache_path)
    _validate_checksum(cache_path, source["checksum"])
    traces = _read_traces(cache_path, manifest["expected_files"])
    selected = select_traces(traces, manifest["selection"]["per_label"])
    rows = build_normalized_rows(
        selected,
        source_uri=source["uri"],
        source_version=manifest["dataset"]["version"],
        source_checksum=source["checksum"],
        selection_rule=f"first {manifest['selection']['per_label']} trace per label after label and trace ID sorting",
    )
    _write_jsonl_atomically(output_path, rows)


def _require_local_hdfs_path(path: Path) -> None:
    """Reject corpus paths that escape the ignored local HDFS workspace."""
    try:
        path.resolve().relative_to(LOCAL_HDFS_ROOT)
    except ValueError as error:
        raise ValueError(f"HDFS corpus paths must be below {LOCAL_HDFS_ROOT}") from error


def _validate_checksum(path: Path, expected: str) -> None:
    algorithm, expected_digest = expected.split(":", maxsplit=1)
    if algorithm != "md5":
        raise ValueError("only the official HDFS_v1 MD5 checksum is currently available")
    actual = hashlib.md5(path.read_bytes()).hexdigest()
    if actual != expected_digest:
        raise ValueError("source checksum mismatch")


def _read_traces(archive_path: Path, expected_files: list[str]) -> dict[str, Trace]:
    with ZipFile(archive_path) as archive:
        if not set(expected_files).issubset(archive.namelist()):
            raise ValueError("archive is missing required HDFS_v1 files")
        labels = {
            row["BlockId"]: row["Label"]
            for row in csv.DictReader(archive.read("anomaly_label.csv").decode("utf-8").splitlines())
        }
        grouped: dict[str, list[tuple[int, str]]] = {}
        for row_number, row in enumerate(
            csv.DictReader(archive.read("HDFS.log_structured.csv").decode("utf-8").splitlines()), start=2
        ):
            trace_id = row.get("BlockId", "")
            if not trace_id:
                raise ValueError("missing trace identifier")
            if trace_id not in labels:
                raise ValueError(f"missing label for trace: {trace_id}")
            grouped.setdefault(trace_id, []).append((row_number, row.get("Content", "")))
    return {trace_id: (labels[trace_id], tuple(coordinates)) for trace_id, coordinates in grouped.items()}


def _write_jsonl_atomically(output_path: Path, rows: list[dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    with NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, output_path)
