# Incident Data Ingestion Specification

> **Source**: Archived from `openspec/changes/dafi-sentinel/specs/incident-data-ingestion/spec.md` on 2026-07-14.
> Initial canonical version (no prior canonical spec existed).

## Purpose

Normalize local seeded incident datasets into deterministic evidence for investigation, security review, retrieval, and ML analysis.

## Requirements

### Requirement: Deterministic Dataset Ingestion

The system MUST parse local logs, alerts, deployments, and metric-like tables into stable records with evidence IDs, timestamps, sources, and normalized fields.

#### Scenario: Ingest seeded dataset

- GIVEN a valid seeded incident dataset
- WHEN ingestion runs
- THEN records have stable evidence IDs
- AND timeline order is repeatable

#### Scenario: Reject malformed row

- GIVEN a row missing timestamp or source
- WHEN ingestion validates the dataset
- THEN validation fails with a structured error
- AND no partial state is committed

### Requirement: Source Traceability

Normalized records MUST retain source metadata for evidence-cited answers and audits, while sensitive values remain redacted. Public-dataset records MUST additionally retain their source provenance and original trace identifier.

#### Scenario: Preserve source reference

- GIVEN an ingested alert from a local file
- WHEN its evidence card is requested
- THEN the card shows evidence ID, source, row or offset, and summary

#### Scenario: Redact source field

- GIVEN a record contains sensitive values
- WHEN downstream capabilities receive it
- THEN sensitive values are replaced with stable redaction markers

### Requirement: Public Benchmark Evidence Provenance

The system MUST retain the canonical source URI, source version/checksum reference, original HDFS block or trace identifier, source row or offset when available, and `Normal` or `Anomaly` benchmark label in each normalized public-dataset evidence record. It MUST preserve labels as source metadata and MUST NOT convert them into incident or attack conclusions.

#### Scenario: Normalize labelled HDFS trace

- GIVEN a validated selected HDFS_v1 trace with source coordinates
- WHEN the trace is normalized
- THEN its evidence record retains provenance, original identifier, coordinates, and label

#### Scenario: Missing traceability field

- GIVEN a selected public trace missing its required original identifier or label
- WHEN normalization is requested
- THEN validation fails and no evidence record is emitted
