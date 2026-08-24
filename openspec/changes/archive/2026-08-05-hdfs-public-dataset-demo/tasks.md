# Tasks: HDFS Public Dataset Demo

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 850–1,050 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 0 research → PR 1 preparation → PR 2 visibility → PR 3 release docs |
| Delivery strategy | auto-forecast |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Rollback boundary |
|---|---|---|---|
| 0 | Verify source and redistribution terms | PR 0; base = tracker | Revert research record only; no data touched. |
| 1 | Local preparation core | PR 1; base = PR 0 | Remove preparer, manifest, ignores, and fixtures. |
| 2 | Opt-in workbench visibility | PR 2; base = PR 1 | Unset seed path and revert API/UI wiring. |
| 3 | Release documentation and proof | PR 3; base = PR 2 | Revert documentation/proof only. |

## Phase 1: Release-Blocking Source Verification (PR 0)

- [x] 1.1 Research and record the official HDFS_v1 canonical artifact URL, exact terms/notice/citation, version, SHA-256, and derivative-redistribution permission with dated primary-source links in `openspec/changes/hdfs-public-dataset-demo/`.
- [x] 1.2 Verify the record against an acceptance checklist; block release, redistribution, and committed-subset work unless every item is confirmed; permit only the user-approved local-only alternative using the published MD5. Test: reviewer can reproduce each claim from the cited official source.

### PR 0 Apply Status — 2026-08-05

| Task | Status | Evidence |
|---|---|---|
| 1.1 | Blocked | `source-verification.md` confirms the official artifact, notice, citations, record version, and MD5, but no authoritative SHA-256 or unambiguous derivative-redistribution permission. |
| 1.2 | Blocked | The acceptance checklist in `source-verification.md` fails the SHA-256 and derivative-permission gates. All subsequent download, subset, redistribution, code, data, and UI work is prohibited. |

## Phase 2: Deterministic Local Preparation (PR 1, strict TDD)

- [x] 2.1 RED: add synthetic `test_hdfs_v1.py` cases for acknowledgement-before-I/O, checksum/shape/label rejection, ordered trace sampling, provenance, atomic output, and byte-identical reruns. No HDFS corpus fixture is committed.
- [x] 2.2 GREEN: create `dafi_sentinel/ingestion/hdfs_v1.py`, pinned `ingestion/manifests/hdfs_v1.json`, and `scripts/prepare_hdfs_v1_demo.py`; validate the published MD5 and normalize only to `.local/hdfs-v1/` using injected/synthetic download tests.
- [x] 2.3 REFACTOR: add `.local/hdfs-v1/` to `.gitignore`, keep validation/sampling pure, and run `uv run pytest tests/dafi_sentinel/test_hdfs_v1.py`; confirm no corpus bytes are tracked.

### PR 1 Verification Remediation — 2026-08-05

- [x] Correct the two fresh-verification critical findings: reject cache/output paths outside ignored `.local/hdfs-v1/`, and make `uv run python scripts/prepare_hdfs_v1_demo.py ...` import the package from repository root. Regression tests cover both boundaries.
- [x] Add runtime coverage through `prepare_local_demo` for an archive row missing `BlockId`; assert validation raises `ValueError` and no normalized output is emitted.
- [x] Final verification remediation: add runtime coverage through `prepare_local_demo` for a selected trace whose benchmark label is missing or blank; assert validation raises `ValueError` and no normalized output is emitted.

## Phase 3: Opt-In Evidence and Analyst Framing (PR 2, strict TDD)

- [x] 3.1 RED: extend `test_api_endpoints.py` for `DAFI_HDFS_DEMO_PATH` opt-in seeding, ownership, retained source URI/version/checksum/trace/label fields, and repeatable analysis inputs; add HDFS evidence fetch stubs in `frontend/src/test/pages.test.tsx`.
- [x] 3.2 GREEN: create `dafi_sentinel/api/demo_seed.py`; wire `api/app.py` and `api/schemas.py` so only validated local JSONL seeds evidence/retrieval documents and default startup stays unseeded.
- [x] 3.3 GREEN: update `frontend/src/api/client.ts` and `pages/EvidenceDetailPage.tsx` to render a distinct provenance panel with trace ID, label, attribution, and the benchmark-not-attack disclaimer.
- [x] 3.4 REFACTOR/verify: run targeted pytest and frontend Vitest; assert no API/UI path converts `Normal`/`Anomaly` into an incident or attack conclusion.

### PR 2 Strict-TDD Evidence — corrected 2026-08-05

| Work item | Safety net | RED | GREEN | Triangulation | Refactor | Actual evidence |
|---|---|---|---|---|---|---|
| 3.1 Opt-in seeding and retained provenance | `uv run pytest tests/dafi_sentinel/test_api_endpoints.py`: 35 passed before the fresh-review regression was added; frontend suite was run before the existing UI changes. | Written: API opt-in/absent-path and frontend provenance tests were added before their PR 2 implementation. | Passed: prior recorded targeted run was 43 passed; the fresh baseline was 35 passed. | Valid local corpus vs absent corpus; HDFS provenance panel vs generic evidence details. | None needed; assertions remain behavior-focused. | Historical PR 2 evidence records the targeted backend/frontend runs; this correction does not claim a rerun of those earlier RED commands. |
| 3.2 Validated local-only loader | `uv run pytest tests/dafi_sentinel/test_api_endpoints.py`: 35 passed before the fresh-review regression was added. | Written: absent-path validation test preceded the loader wiring. | Passed: 35 passed on the fresh baseline. | Existing local JSONL vs absent local JSONL. | Validation stayed before ingestion; no auto-download path added. | The outside-root regression below additionally exercises the existing runtime guard. |
| 3.3 Analyst provenance panel | Existing frontend page tests were run before the PR 2 UI change. | Written: provenance-panel assertions preceded the panel implementation. | Passed: prior recorded frontend run was 33 passed. | HDFS-specific panel vs generic evidence details. | Semantic region and disclaimer assertions retained. | This task has historical frontend evidence only; no new frontend code was changed in this correction. |
| 3.4 Verification and benchmark framing | Targeted backend/frontend suites were run after PR 2 implementation. | Written: no separate RED test; this was a verification/refactor work item. | Passed: prior recorded `uv run pytest`: 249 passed, 1 skipped, 5 xpassed; `npm test`: 33 passed. | API and UI each preserve benchmark metadata without attack conversion. | Full-suite verification completed; no behavior change required. | The recorded full-suite results are retained as historical evidence, not represented as commands run in this correction. |
| Fresh-review safety regression | `uv run pytest tests/dafi_sentinel/test_api_endpoints.py`: 35 passed before this test was added. | Written: `test_default_app_rejects_outside_root_hdfs_path_before_seeding_or_downloading` was added before rerunning the target file; it passed immediately because the guard already existed. | Passed: 36 endpoint tests pass after the test is added; `uv run pytest tests/dafi_sentinel/test_api_endpoints.py tests/dafi_sentinel/test_hdfs_v1.py`: 44 passed. | Outside-root override is contrasted with the existing valid-local and absent-local scenarios. | None needed; production behavior was already correct. | The test asserts startup rejection and verifies the validated-row loader is never reached; the existing seed path never downloads. |
| Final missing/blank-label runtime regression | `uv run pytest tests/dafi_sentinel/test_hdfs_v1.py`: 8 passed before this test was added. | Written first: parameterized missing-label and blank-label archive cases call `prepare_local_demo`; both passed immediately because the existing runtime validation rejects them. | `uv run pytest tests/dafi_sentinel/test_hdfs_v1.py`: 10 passed. | Missing CSV value and explicit blank value exercise distinct `csv.DictReader` outputs through the complete preparation flow. | None needed; existing validation was already concise. | Both cases assert `ValueError` and that the normalized JSONL output does not exist. |

## Phase 4: Release Proof and Documentation (PR 3, strict TDD)

- [x] 4.1 RED: add a reproducibility regression using the synthetic normalized fixture twice through ingestion and `score_anomalies`, asserting stable evidence IDs and analysis inputs.
- [x] 4.2 GREEN: update `README.md` and `PORTFOLIO.md` with gated local preparation, attribution, limitations, rollback, and no-trained-model/benchmark-label framing; do not document or add a subset unless Phase 1 permits it.
- [x] 4.3 REFACTOR/verify: run `uv run pytest` and frontend tests; inspect `git diff --stat` and each chain diff for ≤400 changed lines and only current-slice changes before review.

### PR 3 Strict-TDD Evidence — 2026-08-05

| Work item | Safety net | RED | GREEN | Triangulation | Refactor | Actual evidence |
|---|---|---|---|---|---|---|
| 4.1 Reproducibility regression | `uv run pytest`: 250 passed, 1 skipped, 5 xpassed before the new test file. | Written first as a regression/approval test for existing deterministic preparation, ingestion, and scoring behavior; its stability assertion passed on its first execution. | `uv run pytest tests/dafi_sentinel/test_hdfs_v1_release_proof.py`: 2 passed after documentation was added. | Two independent ingestion/scoring runs; stable IDs and score inputs are compared, and output IDs are checked against ingested evidence. | None needed; no production behavior changed. | Uses synthetic in-memory rows only; no HDFS corpus fixture or network access. |
| 4.2 Documentation and provenance framing | Same full-suite baseline. | The doc-facing contract test was written before the HDFS documentation and failed because README/PORTFOLIO did not contain the official source, MD5-only, local-only, and benchmark-label statements. | Targeted release-proof test passed after the docs were added. | README and PORTFOLIO both assert the shared provenance boundary; README additionally asserts acknowledgement, opt-in seed path, and evidence endpoint guidance. | Kept one concise walkthrough and a scannable boundary table; no API/UI behavior changed. | Docs link primary sources and do not claim an official SHA-256 or redistribution permission. |
| 4.3 Verification and review proof | Targeted release-proof test: 2 passed before final suite rerun. | Not applicable: verification/refactor work item. | `uv run pytest`, frontend tests, `git diff --check`, and diff inspection recorded in apply-progress. | Backend reproducibility and frontend provenance coverage both exercised. | No code refactor required. | Existing worktree contains prior PR 1/PR 2 changes, so the aggregate worktree diff cannot prove a clean PR 3 child diff until normal branch/PR comparison; this slice itself changes only release proof, docs, and SDD task evidence. |
