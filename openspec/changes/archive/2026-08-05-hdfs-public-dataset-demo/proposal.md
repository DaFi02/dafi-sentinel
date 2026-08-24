# Proposal: HDFS Public Dataset Demo

## Intent

Make the portfolio demo credible with reproducible HDFS_v1 operational-log evidence while preserving source attribution and accurately separating benchmark anomalies from cybersecurity attacks.

## Scope

### In Scope
- Add a LogHub HDFS_v1 provenance record: canonical URL, required citation/notice, research/academic-use restriction, version/checksum, and label semantics.
- Provide a checked-in preparation command that downloads to an ignored local cache, verifies the pinned source, deterministically selects a small labelled block-trace subset, and normalizes it into existing evidence rows.
- Retain stable source URI, original block/trace identifier, source row/offset where available, and `Normal`/`Anomaly` benchmark labels. Ship a pinned normalized starter subset only if the source terms permit redistribution; otherwise keep all derived data local and make preparation the demo prerequisite.
- Add fixture-based tests for normalization, reproducible selection, source IDs, labels, and deterministic analysis; document a local visible API/dashboard demo path and attribution in README and PORTFOLIO.

### Out of Scope
- Commercial-use claims, relicensing, redistribution of the full corpus, or committing raw HDFS_v1 files.
- Treating HDFS labels as cyberattacks, training a new model, live SIEM ingestion, or adding other public datasets.

## Capabilities

### New Capabilities
- `public-dataset-demo`: attributed, local-only preparation and presentation of a reproducible public operational-log demo corpus.

### Modified Capabilities
- `incident-data-ingestion`: retain public-dataset provenance, original identifiers, and benchmark labels in normalized evidence.
- `investigation-workbench`: expose a documented, locally prepared HDFS demo path with evidence provenance visible to the analyst.

## Approach

Use a source-pinned manifest and deterministic selector, never checked-in raw data. The preparer MUST require explicit acknowledgement of LogHub terms, cache downloads outside version control, validate checksum/shape, emit normalized JSONL locally, and fail clearly if source access or validation fails. A redistribution gate decides whether a small normalized starter subset is committed; otherwise the existing workbench seeds locally from that output. Labels remain benchmark metadata, never analyst conclusions.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `dafi_sentinel/ingestion/` | Modified | HDFS normalization and provenance validation |
| `dafi_sentinel/api/` | Modified | Local demo seeding/visible evidence path |
| `tests/dafi_sentinel/` | Modified | Reproducibility and traceability guards |
| `README.md`, `PORTFOLIO.md` | Modified | Setup, attribution, and honest label framing |
| `.gitignore`, `scripts/` | Modified/New | Exclude cache/output; preparation command |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Terms prohibit intended redistribution | Medium | Commit manifests/code only; require acknowledgement and link official terms. |
| Upstream changes/disappears | Medium | Pin URL/checksum and fail validation; document regeneration. |
| Labels are misrepresented as attacks | Medium | Preserve semantics and repeat operational-only disclaimer in UI/docs. |

## Rollback Plan

Remove demo seeding, command, and documentation; delete ignored local cache/output. Existing ingestion and workbench fixtures remain unchanged.

## Dependencies

- LogHub HDFS_v1 availability and continued compliance with its research/academic-use attribution terms.

## Success Criteria

- [ ] A fresh authorized local setup reproduces the same selected evidence IDs, provenance, labels, and analysis inputs.
- [ ] Repository history contains no full raw corpus; a committed starter subset, if any, passes the redistribution gate.
- [ ] Demo evidence visibly identifies HDFS_v1 and labels it as operational benchmark data, not cybersecurity attack evidence.
- [ ] Tests cover malformed source, label, ID, and deterministic-selection cases.

## Delivery Forecast

Decision needed before apply: No
Chained PRs recommended: Yes
400-line budget risk: High
