# HDFS Public Dataset Demo Archived

The approved local-only HDFS_v1 integration is archived. Canonical OpenSpec requirements now include public-benchmark provenance and analyst-visible benchmark framing; no code or scope was changed during archival.

## Archive outcome

| Topic | Result |
|---|---|
| Final verification | PASS WITH WARNINGS |
| Completed tasks | 12/12; no unchecked implementation tasks |
| Canonical specs | `incident-data-ingestion` and `investigation-workbench` updated |
| Local-only boundary | Preserved: explicit acknowledgement, official MD5 validation, and ignored `.local/hdfs-v1/` paths |
| Corpus/subset release | Blocked |

## Retained legal and data gate

Primary-source verification did not establish an official SHA-256 or unambiguous permission to redistribute a normalized derivative. Therefore redistribution, committed corpus or subsets, and related release claims remain blocked. This archive preserves only the approved local-only HDFS integration; it does not grant any broader data right.

## Verification warnings

1. The frontend production build passed but emitted the existing Vite warning for a minified chunk greater than 500 kB.
2. Existing/dependency deprecation warnings and expected xpasses appeared in test output; no test failed.

## Engram traceability

| Artifact | Observation ID |
|---|---:|
| Proposal | #941 |
| Specification | #942 |
| Design | #943 |
| Tasks | #944 |
| Final verification report | #950 |

## Archive checks

- [x] Delta specifications merged before archive move.
- [x] Canonical specs preserve requirements not addressed by the delta.
- [x] Archived task record has no unchecked implementation tasks.
- [x] Archive contains proposal, specifications, design, tasks, verification report, source verification, and apply progress.
- [x] Active change directory no longer contains this change.
