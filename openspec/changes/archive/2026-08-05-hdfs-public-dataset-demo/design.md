# Design: HDFS Public Dataset Demo

## Technical Approach

Add a code-and-manifest-only local preparation path for LogHub HDFS_v1. A checked-in manifest pins the source and its terms; a Python CLI requires explicit acknowledgement, downloads to an ignored cache, validates the input, deterministically selects labelled traces, and writes ignored normalized JSONL. The dev-only API factory optionally seeds that JSONL into the existing in-memory evidence/retrieval services. No raw or derived corpus is committed unless a separately documented redistribution review permits it (the default is **no starter subset**).

## Architecture Decisions

| Decision | Alternatives / trade-off | Rationale |
|---|---|---|
| Manifest plus explicit CLI acknowledgement | Hard-code URL; interactive prompt | A versioned JSON manifest makes provenance reviewable; `--acknowledge-loghub-terms` is scriptable and fails before I/O. |
| Local cache and output only | Commit raw data or a starter fixture | Terms and upstream size are uncertain. Keep `.local/hdfs-v1/{cache,output}` ignored; tests use synthetic fixtures only. |
| Deterministic trace-level sampler | Random sample; row-level sample | Sort by label then trace ID and take configured per-label counts. A trace is the meaningful HDFS unit and reproducibility is inspectable. |
| Provenance in existing `fields` plus `SourceMetadata` | Domain-model migration | `EvidenceResponse` already exposes `source_*` and `fields`; namespaced immutable fields avoid widening all existing contracts. |
| Explicit opt-in API seed | Auto-download/prepare at server boot | `DAFI_HDFS_DEMO_PATH` points to validated local JSONL. The server never downloads data, accepts terms, or claims a prepared demo implicitly. |

The manifest MUST contain canonical URL, official notice/citation, use restriction, version, SHA-256, expected files/columns, allowed labels, and sampler counts. Its actual URL, checksum, and notice are release-blocking inputs: do not invent or guess them.

## Data Flow

```text
manifest + --acknowledge-loghub-terms
  -> ignored download cache -> checksum/shape validation
  -> sorted trace sampler -> normalizer -> ignored normalized JSONL
  -> DAFI_HDFS_DEMO_PATH -> dev factory -> evidence + retrieval index
  -> /evidence -> dashboard provenance/disclaimer
```

Each normalized line follows the existing ingestion input shape. `source.uri` is the canonical URL and `source.row`/`offset` retain source coordinates. Required namespaced fields are:

```python
{
  "dataset.name": "LogHub HDFS_v1",
  "dataset.version": str, "dataset.sha256": str,
  "dataset.trace_id": str, "dataset.label": "Normal" | "Anomaly",
  "dataset.label_semantics": "Operational benchmark metadata; not a cybersecurity attack conclusion.",
  "dataset.selection_rule": str,
}
```

The normalizer creates stable `incident_id` from the trace ID and a deterministic synthetic timestamp based on selected order (clearly marked in fields), because HDFS labels/traces do not supply incident timestamps. It rejects duplicate identifiers, missing coordinates/trace IDs, unsupported labels, malformed checksums, and empty selections before atomically replacing output. It passes rows through `ingest_incident_dataset` and `RedactionService`; evidence IDs therefore retain the existing stable source-coordinate scheme.

## File Changes

| File | Action | Description |
|---|---|---|
| `dafi_sentinel/ingestion/hdfs_v1.py` | Create | Manifest loading, validation, trace grouping/sampling, normalization, JSONL I/O. |
| `dafi_sentinel/ingestion/manifests/hdfs_v1.json` | Create | Pinned source, acknowledgement text, schema and selection rule; no corpus bytes. |
| `scripts/prepare_hdfs_v1_demo.py` | Create | Explicit local CLI; cache/output arguments default to ignored paths. |
| `dafi_sentinel/api/demo_seed.py` | Create | Load validated normalized JSONL, save owned evidence, and build trace-backed `Document`s. |
| `dafi_sentinel/api/app.py`, `api/schemas.py` | Modify | Opt-in dev seed and structured public-dataset presentation contract. |
| `frontend/src/api/client.ts`, `pages/Evidence*Page.tsx` | Modify | Render a distinct HDFS provenance panel and benchmark-not-attack disclaimer. |
| `.gitignore` | Modify | Ignore `.local/hdfs-v1/` and any configured demo output. |
| `tests/dafi_sentinel/fixtures/hdfs_v1_*`, `test_hdfs_v1.py`, `test_api_endpoints.py` | Create/Modify | Synthetic parsing, failures, reproducibility, seeding, and API visibility tests. |
| `frontend/src/test/pages.test.tsx` | Modify | Assert visible attribution, label, trace ID, and disclaimer. |
| `README.md`, `PORTFOLIO.md` | Modify | Local preparation/run steps, attribution, limitations, and no-trained-model claim. |

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Unit | acknowledgement, checksum/shape/label/duplicate rejection; ordered sampler; normalized IDs/provenance | Synthetic tiny HDFS-like fixtures; no network or raw corpus. |
| Integration | CLI output is atomic and repeatable; output loads into existing ingestion and seeded app | Temporary paths, injected downloader/manifest, two-run byte/ID comparison. |
| API/UI | opt-in seed only; owned evidence exposes fields; attribution/disclaimer visible | FastAPI `TestClient`; Vitest fetch stubs and page assertions. |
| Regression | analysis inputs and `score_anomalies` are repeatable | Feed the same normalized fixture twice with the existing seeded analysis API. |

## Migration / Rollout

No migration. Default behavior stays unseeded. Roll back by unsetting `DAFI_HDFS_DEMO_PATH`, removing the optional seed code, and deleting ignored local data.

## Work Units / PR Boundaries

1. **PR A — preparation core**: manifest, ignore rules, normalizer/CLI, synthetic tests (target ≤400 lines).
2. **PR B — workbench visibility**: opt-in seed, API contract, dashboard panel, backend/frontend tests (target ≤400 lines).
3. **PR C — documentation and release gate**: README/PORTFOLIO, attribution verification, final reproducibility checks (target ≤250 lines).

## Open Questions

- [ ] Confirm the official HDFS_v1 canonical artifact URL, version, SHA-256, exact required notice, and whether normalized derivatives may be redistributed. Until confirmed, the manifest must remain a template and no subset may be committed.
