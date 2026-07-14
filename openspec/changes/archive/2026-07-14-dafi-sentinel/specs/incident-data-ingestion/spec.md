# Incident Data Ingestion Specification

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

Normalized records MUST retain source metadata for evidence-cited answers and audits, while sensitive values remain redacted.

#### Scenario: Preserve source reference

- GIVEN an ingested alert from a local file
- WHEN its evidence card is requested
- THEN the card shows evidence ID, source, row or offset, and summary

#### Scenario: Redact source field

- GIVEN a record contains sensitive values
- WHEN downstream capabilities receive it
- THEN sensitive values are replaced with stable redaction markers
