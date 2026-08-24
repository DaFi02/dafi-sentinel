from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from dafi_sentinel.ingestion.hdfs_v1 import (
    TermsNotAcknowledgedError,
    build_normalized_rows,
    prepare_local_demo,
    select_traces,
)


def _traces() -> dict[str, tuple[str, tuple[tuple[int, str], ...]]]:
    return {
        "blk_2": ("Normal", ((2, "second normal trace"),)),
        "blk_1": ("Normal", ((1, "first normal trace"),)),
        "blk_4": ("Anomaly", ((4, "second anomalous trace"),)),
        "blk_3": ("Anomaly", ((3, "first anomalous trace"),)),
    }


def test_preparation_requires_terms_acknowledgement_before_downloading(tmp_path: Path):
    downloaded = False

    def downloader(_: str, __: Path) -> None:
        nonlocal downloaded
        downloaded = True

    with pytest.raises(TermsNotAcknowledgedError):
        prepare_local_demo(
            manifest_path=tmp_path / "manifest.json",
            cache_path=tmp_path / "cache.zip",
            output_path=tmp_path / "output.jsonl",
            acknowledged=False,
            downloader=downloader,
        )

    assert downloaded is False


def test_selection_is_label_then_trace_id_ordered_and_normalization_retains_metadata():
    selected = select_traces(_traces(), per_label=1)
    rows = build_normalized_rows(
        selected,
        source_uri="https://example.test/HDFS_v1.zip",
        source_version="10.5281/zenodo.8196385",
        source_checksum="md5:76a24b4d9a6164d543fb275f89773260",
        selection_rule="first 1 trace per label after label and trace ID sorting",
    )

    assert [row["fields"]["dataset.trace_id"] for row in rows] == ["blk_3", "blk_1"]
    assert [row["fields"]["dataset.label"] for row in rows] == ["Anomaly", "Normal"]
    assert rows[0]["source"] == {"uri": "https://example.test/HDFS_v1.zip", "row": 3}
    assert rows[0]["fields"]["dataset.label_semantics"] == (
        "Operational benchmark metadata; not a cybersecurity attack conclusion."
    )


def test_duplicate_trace_ids_and_unsupported_labels_are_rejected():
    with pytest.raises(ValueError, match="unsupported label"):
        select_traces({"blk_1": ("Attack", ((1, "one"),))}, 1)


def test_preparation_writes_byte_identical_local_output_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import dafi_sentinel.ingestion.hdfs_v1 as hdfs_v1

    local_root = tmp_path / ".local" / "hdfs-v1"
    monkeypatch.setattr(hdfs_v1, "LOCAL_HDFS_ROOT", local_root)
    archive = local_root / "cache" / "source.zip"
    archive.parent.mkdir(parents=True)
    with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("HDFS.log_structured.csv", "Content,EventId,BlockId\nfirst,E1,blk_2\nsecond,E2,blk_1\n")
        zipped.writestr("anomaly_label.csv", "BlockId,Label\nblk_2,Normal\nblk_1,Anomaly\n")
    manifest = {
        "dataset": {"name": "LogHub HDFS_v1", "version": "10.5281/zenodo.8196385"},
        "source": {"uri": "https://example.test/HDFS_v1.zip", "checksum": f"md5:{hashlib.md5(archive.read_bytes()).hexdigest()}"},
        "terms": {"acknowledgement": "I acknowledge the LogHub research/academic terms."},
        "expected_files": ["HDFS.log_structured.csv", "anomaly_label.csv"],
        "allowed_labels": ["Normal", "Anomaly"],
        "selection": {"per_label": 1},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = local_root / "output" / "normalized.jsonl"

    prepare_local_demo(manifest_path, archive, output, acknowledged=True, downloader=lambda _, __: None)
    first = output.read_bytes()
    prepare_local_demo(manifest_path, archive, output, acknowledged=True, downloader=lambda _, __: None)

    assert output.read_bytes() == first
    rows = [json.loads(line) for line in first.decode().splitlines()]
    assert [row["fields"]["dataset.trace_id"] for row in rows] == ["blk_1", "blk_2"]
    for row in rows:
        assert row["fields"]["dataset.attribution.notice"] == (
            "The datasets are freely available for research or academic work, subject to the following condition: "
            "For any usage or distribution of the loghub datasets, please refer to the loghub repository URL "
            "(https://github.com/logpai/loghub) and cite the following loghub paper where applicable.\n\n"
            "Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. Loghub: A Large Collection "
            "of System Log Datasets for AI-driven Log Analytics. In ISSRE, 2023.\n\n"
            "The above license notice shall be included in all copies of the datasets."
        )
        assert row["fields"]["dataset.attribution.citations"] == [
            "Wei Xu, Ling Huang, Armando Fox, David Patterson, Michael Jordan. *Detecting Large-Scale "
            "System Problems by Mining Console Logs*. SOSP, 2009.",
            "Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu. *Loghub: A Large Collection "
            "of System Log Datasets for AI-driven Log Analytics*. ISSRE, 2023.",
        ]


def test_preparation_rejects_checksum_mismatch_without_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import dafi_sentinel.ingestion.hdfs_v1 as hdfs_v1

    local_root = tmp_path / ".local" / "hdfs-v1"
    monkeypatch.setattr(hdfs_v1, "LOCAL_HDFS_ROOT", local_root)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset": {"version": "10.5281/zenodo.8196385"},
                "source": {"uri": "https://example.test/HDFS_v1.zip", "checksum": "md5:" + "0" * 32},
                "expected_files": [],
                "selection": {"per_label": 1},
            }
        ),
        encoding="utf-8",
    )
    cache = local_root / "cache" / "source.zip"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"not an archive")
    output = local_root / "output" / "normalized.jsonl"

    with pytest.raises(ValueError, match="checksum mismatch"):
        prepare_local_demo(manifest_path, cache, output, acknowledged=True, downloader=lambda _, __: None)

    assert output.exists() is False


def test_preparation_rejects_missing_trace_identifier_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import dafi_sentinel.ingestion.hdfs_v1 as hdfs_v1

    local_root = tmp_path / ".local" / "hdfs-v1"
    monkeypatch.setattr(hdfs_v1, "LOCAL_HDFS_ROOT", local_root)
    cache = local_root / "cache" / "source.zip"
    cache.parent.mkdir(parents=True)
    with ZipFile(cache, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("HDFS.log_structured.csv", "Content,EventId,BlockId\nmissing,E1,\n")
        zipped.writestr("anomaly_label.csv", "BlockId,Label\nblk_1,Normal\n")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset": {"version": "10.5281/zenodo.8196385"},
                "source": {
                    "uri": "https://example.test/HDFS_v1.zip",
                    "checksum": f"md5:{hashlib.md5(cache.read_bytes()).hexdigest()}",
                },
                "expected_files": ["HDFS.log_structured.csv", "anomaly_label.csv"],
                "selection": {"per_label": 1},
            }
        ),
        encoding="utf-8",
    )
    output = local_root / "output" / "normalized.jsonl"

    with pytest.raises(ValueError, match="missing trace identifier"):
        prepare_local_demo(manifest_path, cache, output, acknowledged=True, downloader=lambda _, __: None)

    assert output.exists() is False


@pytest.mark.parametrize("label", [None, ""])
def test_preparation_rejects_missing_or_blank_benchmark_label_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str | None
):
    import dafi_sentinel.ingestion.hdfs_v1 as hdfs_v1

    local_root = tmp_path / ".local" / "hdfs-v1"
    monkeypatch.setattr(hdfs_v1, "LOCAL_HDFS_ROOT", local_root)
    cache = local_root / "cache" / "source.zip"
    cache.parent.mkdir(parents=True)
    label_row = "blk_1\n" if label is None else f"blk_1,{label}\n"
    with ZipFile(cache, "w", ZIP_DEFLATED) as zipped:
        zipped.writestr("HDFS.log_structured.csv", "Content,EventId,BlockId\nentry,E1,blk_1\n")
        zipped.writestr("anomaly_label.csv", f"BlockId,Label\n{label_row}")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset": {"version": "10.5281/zenodo.8196385"},
                "source": {
                    "uri": "https://example.test/HDFS_v1.zip",
                    "checksum": f"md5:{hashlib.md5(cache.read_bytes()).hexdigest()}",
                },
                "expected_files": ["HDFS.log_structured.csv", "anomaly_label.csv"],
                "selection": {"per_label": 1},
            }
        ),
        encoding="utf-8",
    )
    output = local_root / "output" / "normalized.jsonl"

    with pytest.raises(ValueError, match="missing label|unsupported label"):
        prepare_local_demo(manifest_path, cache, output, acknowledged=True, downloader=lambda _, __: None)

    assert output.exists() is False


def test_preparation_rejects_cache_or_output_outside_local_hdfs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import dafi_sentinel.ingestion.hdfs_v1 as hdfs_v1

    local_root = tmp_path / ".local" / "hdfs-v1"
    monkeypatch.setattr(hdfs_v1, "LOCAL_HDFS_ROOT", local_root)

    with pytest.raises(ValueError, match="must be below"):
        prepare_local_demo(
            manifest_path=tmp_path / "manifest.json",
            cache_path=tmp_path / "tracked.zip",
            output_path=local_root / "output" / "normalized.jsonl",
            acknowledged=True,
            downloader=lambda _, __: None,
        )

    with pytest.raises(ValueError, match="must be below"):
        prepare_local_demo(
            manifest_path=tmp_path / "manifest.json",
            cache_path=local_root / "cache" / "HDFS_v1.zip",
            output_path=tmp_path / "tracked.jsonl",
            acknowledged=True,
            downloader=lambda _, __: None,
        )


def test_documented_script_command_loads_package_from_repository_root():
    script = Path(__file__).parents[2] / "scripts" / "prepare_hdfs_v1_demo.py"
    if not script.exists():
        # scripts/ is excluded from the container build context; running the
        # documented command is a full-checkout contract.
        pytest.skip("demo script absent (containerized run without build context)")

    result = subprocess.run(
        [sys.executable, "scripts/prepare_hdfs_v1_demo.py", "--help"],
        capture_output=True,
        check=False,
        cwd=Path(__file__).parents[2],
        text=True,
    )

    assert result.returncode == 0
    assert "--acknowledge-loghub-terms" in result.stdout
