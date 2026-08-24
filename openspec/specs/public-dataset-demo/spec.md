# Public Dataset Demo Specification

## Purpose

Prepare an attributed, reproducible HDFS_v1 operational-benchmark demo locally without tracking the raw corpus.

## Requirements

### Requirement: Acknowledged Local Preparation

The system MUST publish a pinned HDFS_v1 source record containing the canonical source URI, required attribution/notice, use restriction, version, checksum, label semantics, and selection rule. Preparation MUST require explicit acknowledgement of those terms and MUST NOT run without it.

#### Scenario: Prepare after acknowledgement

- GIVEN the pinned record and an explicit terms acknowledgement
- WHEN preparation is requested
- THEN the system permits local preparation
- AND records the declared source provenance in its output

#### Scenario: Terms not acknowledged

- GIVEN no explicit terms acknowledgement
- WHEN preparation is requested
- THEN the system fails before download or output generation

### Requirement: Validated Deterministic Local Corpus

The system MUST validate the downloaded source against its pinned checksum and required HDFS_v1 shape, including a trace identifier and `Normal` or `Anomaly` label. For identical pinned input and selection rule, it MUST emit the same ordered selected trace identifiers and normalized analysis inputs. Raw and derived corpus files MUST remain in ignored local paths and MUST NOT be committed to repository history.

#### Scenario: Reproduce selected evidence

- GIVEN two authorized preparations with identical pinned input
- WHEN each applies the published selection rule
- THEN their ordered selected trace identifiers and analysis inputs are identical

#### Scenario: Reject invalid source

- GIVEN a source with a checksum mismatch, missing trace identifier, or unsupported label
- WHEN preparation validates it
- THEN it fails without emitting a normalized corpus

### Requirement: Attribution and Benchmark Framing

The system MUST present source attribution and the statement that HDFS_v1 labels are operational-benchmark metadata, not cybersecurity attack conclusions, wherever the prepared demo is introduced to an analyst.

#### Scenario: View prepared demo

- GIVEN locally prepared HDFS_v1 evidence
- WHEN an analyst opens the demo path
- THEN attribution and the operational-benchmark disclaimer are visible
