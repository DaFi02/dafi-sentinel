# Delta for Incident Data Ingestion

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Source Traceability

Normalized records MUST retain source metadata for evidence-cited answers and audits, while sensitive values remain redacted. Public-dataset records MUST additionally retain their source provenance and original trace identifier.
(Previously: Normalized records retained source metadata for evidence-cited answers and audits.)

#### Scenario: Preserve source reference

- GIVEN an ingested alert from a local file
- WHEN its evidence card is requested
- THEN the card shows evidence ID, source, row or offset, and summary

#### Scenario: Redact source field

- GIVEN a record contains sensitive values
- WHEN downstream capabilities receive it
- THEN sensitive values are replaced with stable redaction markers
