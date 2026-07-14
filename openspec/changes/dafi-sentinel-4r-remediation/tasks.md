# Tasks: DAFI Sentinel 4R Remediation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1850-2100 total (PR-A ~250, PR-B ~700, PR-C ~900, all size:exception except PR-A) |
| 400-line budget risk | High for PR-B and PR-C, Low for PR-A |
| Chained PRs recommended | Yes |
| Suggested split | PR-A hotfix -> PR-B hexagonal -> PR-C production |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low|Medium|High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Hotfix CRITICAL | PR-A | base=main; ~250 lines; fits 400 budget; no size:exception |
| 2 | Hexagonal cleanup | PR-B | base=main (stacked after PR-A); ~700 lines; size:exception (precedent PR3-PR6 in archived change) |
| 3 | Production-readiness | PR-C | base=main (stacked after PR-A+PR-B); ~900 lines; size:exception (precedent PR3-PR6) |

## PR-A: Hotfix CRITICAL (~250 lines, fits 400 budget)

> **Status: applied** — 10 commits on `dafi-sentinel-4r-remediation/pr-a-hotfix`, PR #2 at https://github.com/DaFi02/dafi-sentinel/pull/2. Diff: 887 lines (size:exception — see PR body for rationale).

- [x] A.1 Add `forbidOnly` to `pyproject.toml` and `frontend/vite.config.ts` (strict TDD: addopts first, then vitest config) [refs: R3 F1] [files: pyproject.toml, frontend/vite.config.ts]
- [x] A.2 Delete `EvidenceRepositoryAdapter` from `services.py`; remove imports/callers; run `uv run pytest` to confirm no regression [refs: R2 crit#1] [files: dafi_sentinel/api/services.py]
- [x] A.3 Delete `RecentEvidenceCache` from `services.py`; remove imports/callers; run `uv run pytest` [refs: R2 crit#2] [files: dafi_sentinel/api/services.py]
- [x] A.4 Delete `base64_to_png` from `services.py`; remove imports/callers; run `uv run pytest` [refs: R2 crit#3] [files: dafi_sentinel/api/services.py]
- [x] A.5 Delete `useMe`/`useLogin`/`useLogout` in `queries.ts`; update consumers to call endpoints directly [refs: R2 crit#4] [files: frontend/src/api/queries.ts, frontend/src/pages/LoginPage.tsx]
- [x] A.6 Inject `clock: Callable[[], datetime]` into `WorkbenchService.__init__` and `_build_audit_record`; thread through `_record_audit`; default to `datetime.utcnow` for back-compat [refs: R3 F2, R2 high#4] [files: dafi_sentinel/orchestration/graph.py, dafi_sentinel/api/services.py]
- [x] A.7 Add `app.exception_handler(ChartValidationError)` returning HTTP 422 with structured payload in `app.py` [refs: R3 F3] [files: dafi_sentinel/api/app.py]
- [x] A.8 Add parametrized `test_charts_endpoint_rejects_invalid_spec` covering empty `evidence_ids`, blank `evidence_id`, blank `x` (RED before A.7 ships, GREEN after) [refs: R3 F3] [files: tests/dafi_sentinel/test_charts_validation.py]
- [x] A.9 Add `test_orchestration_audit_timestamps_are_deterministic_with_injected_clock`; assert frozen clock -> equal timestamps (RED before A.6) [refs: R3 F2] [files: tests/dafi_sentinel/test_orchestration_audit_timestamps.py]
- [x] A.10 Remove plaintext `hunter2!` from `README.md:112-113` and `app.py:386`; replace with dev-only random-on-boot or `DAFI_DEV_PASSWORD` env-var [refs: R1 high#1] [files: dafi_sentinel/api/app.py, README.md]
- [x] A.11 Mark `default_workbench_app` as dev-only posture in docstring and README; add `DAFI_PRODUCTION_POSTURE` env-gated section [refs: R4 crit#1] [files: dafi_sentinel/api/app.py, README.md]
- [x] A.12 Add `test_login_error_message_does_not_leak_username_existence`; assert identical error string for unknown user vs wrong password [refs: R3 F26] [files: tests/dafi_sentinel/test_auth.py]

## PR-B: Hexagonal Cleanup (~700 lines, size:exception)

Rationale: exceeds 400-line budget; precedent PR3-PR6 in archived `2026-07-14-dafi-sentinel` change accepted `size:exception` for cross-cutting refactors of similar scope.

- [x] B.1 Widen `WorkbenchService.evidence` to `EvidenceRepository` Protocol; add `isinstance` guard at construction [refs: R2 crit#5] [files: dafi_sentinel/api/services.py, dafi_sentinel/storage/contracts.py]
- [x] B.2 Inject `RetrievalIndex` into `WorkbenchService.__init__` instead of always building fresh `InMemoryRetrievalIndex`; keep default factory in `default_workbench_app` [refs: R2 crit#6, R2 high#9] [files: dafi_sentinel/api/services.py, dafi_sentinel/api/app.py]
- [x] B.3 Honor `session_id` field in `InMemoryAuditRepository.write_audit`; index records by `(actor_id, session_id)` [refs: R2 crit#7] [files: dafi_sentinel/api/services.py]
- [x] B.4 Add `@runtime_checkable` to `AuditRepository` and `EvidenceRepository` in `storage/contracts.py` (asymmetry fix) [refs: R2 med] [files: dafi_sentinel/storage/contracts.py]
- [x] B.5 Extract `AuditAction` and `AuditReason` enums; replace 11 magic strings across `services.py`, `graph.py`, `app.py` [refs: R2 high#3] [files: dafi_sentinel/api/audit_enums.py, dafi_sentinel/api/services.py, dafi_sentinel/orchestration/graph.py, dafi_sentinel/api/app.py]
- [x] B.6 Refactor 91-line approval node in `graph.py:300-389` into `_check_authorization`, `_validate_payload`, `_record_decision` helpers [refs: R2 high#1] [files: dafi_sentinel/orchestration/graph.py]
- [x] B.7 Delete legacy `approver_id` fallback in `_coerce_approval` (`graph.py:519-525`); require explicit approver [refs: R2 high#10, R3 F19] [files: dafi_sentinel/orchestration/graph.py]
- [x] B.8 Move `_SYSTEM_APPROVER` declaration before first reference (`graph.py:606-610` -> top of module) [refs: R2 med, R3 F8] [files: dafi_sentinel/orchestration/graph.py]
- [x] B.9 Add `test_orchestration_system_approver_passes_authorization_check` (RED before B.7 ships) [refs: R3 F8] [files: tests/dafi_sentinel/test_orchestration_approvals.py]
- [x] B.10 Fix `setState` in render in `RolesPage.tsx:9-13` via `useEffect` + session bootstrap [refs: R2 high#5, R3 F4] [files: frontend/src/pages/RolesPage.tsx]
- [x] B.11 Remove `enabled` parameter from frontend mutations in `queries.ts`; rely on `useMutation` defaults [refs: R2 high#6] [files: frontend/src/api/queries.ts]
- [x] B.12 Implement `DAFI_DEV_NO_CSP_META` toggle: emit `<meta http-equiv="Content-Security-Policy">` in `index.html` unless env disables it for dev [refs: R2 high#7] [files: frontend/index.html, frontend/src/main.tsx]
- [x] B.13 Inject clock into `sweep_stale_pauses`; replace `time.sleep` in test with `Clock.sleep` injection [refs: R3 F6] [files: dafi_sentinel/orchestration/graph.py, tests/dafi_sentinel/test_sweeper.py]
- [x] B.14 Switch session_id field in login audit to SHA-256-truncated hash (first 16 hex) [refs: R3 F18] [files: dafi_sentinel/api/auth.py, dafi_sentinel/api/services.py]
- [x] B.15 Document `InMemoryRetrievalIndex` as "recall-only, order-stable" in `retrieval/contracts.py` docstring [refs: R3 F24] [files: dafi_sentinel/retrieval/contracts.py]
- [x] B.16 Re-export orchestration symbols (`WorkbenchService`, `build_workbench_graph`, `sweep_stale_pauses`) from `orchestration/__init__.py` [refs: R2 med] [files: dafi_sentinel/orchestration/__init__.py]
- [x] B.17 Add `test_validation_collects_multiple_errors_per_row` (parametrized, 3+ cases) [refs: R3 F17] [files: tests/dafi_sentinel/test_validation.py]
- [x] B.18 Parametrize redaction tests across `aws_*`, `github_pat_*`, JWT, generic `api_key=` (covers R1 med#11) [refs: R3 F10] [files: tests/dafi_sentinel/test_redaction.py]

## PR-C: Production-Readiness (~900 lines, size:exception)

Rationale: exceeds 400-line budget; precedent PR3-PR6 in archived `2026-07-14-dafi-sentinel` change accepted `size:exception` for cross-cutting hardening of similar scope.

- [x] C.1 Add `production_graph()` factory example with `PostgresSaver` gated on `DAFI_PRODUCTION_GRAPH=1` env var; in-memory remains default [refs: R4 crit#2, R4 high#2] [files: dafi_sentinel/api/app.py, README.md]
- [x] C.2 Mount `sweep_stale_pauses` as FastAPI `lifespan` background task with explicit cancellation on shutdown; add lifespan test [refs: R4 crit#3] [files: dafi_sentinel/api/app.py, tests/dafi_sentinel/test_lifespan.py]
- [x] C.3 Add `CORSMiddleware`, `TrustedHostMiddleware`, `HTTPSRedirectMiddleware`, HSTS headers (production-graph only) [refs: R1 high#4] [files: dafi_sentinel/api/app.py]
- [x] C.4 Add rate limits (slowapi) + payload-size caps on `/sessions`, `/qa`, `/charts` [refs: R1 high#3] [files: dafi_sentinel/api/app.py, dafi_sentinel/api/schemas.py]
- [x] C.5 Add `max_length=256` to `LoginRequest.password` and `max_length=2048` to `QuestionRequest.question` [refs: R1 high#5] [files: dafi_sentinel/api/schemas.py]
- [x] C.6 Server-side approver lookup in `_evaluate_approver`: trust `ActorStore.get_user`, not caller-supplied `UserRef` [refs: R1 high#2] [files: dafi_sentinel/orchestration/graph.py, dafi_sentinel/storage/contracts.py]
- [x] C.7 Add `Cache-Control: no-store` on `/sessions` and `/audits` responses [refs: R1 high#4] [files: dafi_sentinel/api/app.py]
- [x] C.8 Add React `ErrorBoundary` with retry button around `<App>`; bump `QueryClient` `retry: 1` [refs: R4 crit#4] [files: frontend/src/main.tsx, frontend/src/App.tsx, frontend/src/components/ErrorBoundary.tsx]
- [x] C.9 Add `logging.basicConfig` + `request_id` middleware (UUID4 per request, propagated to audits) [refs: R4 high#4] [files: dafi_sentinel/api/app.py]
- [x] C.10 Add `threading.RLock` to `InMemoryEvidenceRepository` and `InMemoryAuditRepository`; reads remain lock-free [refs: R1 med#9, R4 high#6] [files: dafi_sentinel/api/services.py]
- [x] C.11 Add `DELETE /sessions/{token}` deprecation warning (still functional, scheduled for removal) [refs: R4 high#7, R1 med] [files: dafi_sentinel/api/app.py]
- [x] C.12 Fix cookie+Bearer precedence: when both present, document and test Bearer-wins (RFC 6750) [refs: R2 med] [files: dafi_sentinel/api/auth.py, tests/dafi_sentinel/test_auth.py]
- [x] C.13 Expand redaction regex to cover `aws_*`, `github_pat_*`, JWT (`eyJ...`), generic `api_key=` (if not already covered by B.18) [refs: R1 med#11] [files: dafi_sentinel/security/policy.py]
- [x] C.14 Parametrize `inspect_user_request` triggers across prompt-injection patterns (RED before changes) [refs: R3 F11, R4 high#3] [files: tests/dafi_sentinel/test_inspect_user_request.py]
- [x] C.15 Add ML edge case tests: empty features, NaN, single-class, constant column [refs: R3 F12] [files: tests/dafi_sentinel/test_ml_edge_cases.py]
- [x] C.16 Add chart-renderer edge case tests: zero-height figure, unicode labels, empty series [refs: R3 F13] [files: tests/dafi_sentinel/test_charts_edge_cases.py]
- [x] C.17 Fix pgvector SQL-injection f-string in `retrieval/pgvector.py` with `sql.Identifier` and `sql.Literal` [refs: R2 med] [files: dafi_sentinel/retrieval/pgvector.py]
- [x] C.18 Add Ingestion edge case tests: empty CSV, BOM rows, mixed line endings, missing required column [refs: R3 F9] [files: tests/dafi_sentinel/test_ingestion_edges.py]
- [x] C.19 Remove default seeded dev credentials in `LoginPage`; require explicit input [refs: R2 med] [files: frontend/src/pages/LoginPage.tsx]
- [x] C.20 Add `<ApiErrorMessage />` component or `useErrorMessage()` hook in frontend; dedup error rendering [refs: R2 high#5] [files: frontend/src/components/ApiErrorMessage.tsx, frontend/src/api/queries.ts]
- [x] C.21 Split `test_logout_clears_session_cookie` into 5 named assertions (cookie cleared, body shape, status, header, audit) [refs: R3 F14] [files: tests/dafi_sentinel/test_logout.py]
- [x] C.22 Add `pytest.mark.timeout(5)` to pgvector-unreachable test; assert bounded wait [refs: R3 F15] [files: tests/dafi_sentinel/test_pgvector_unreachable.py]

## Execution Order

- **PR-A is the entry point.** It must be merged to `main` before PR-B opens. PR-A fixes CRITICALs that PR-B's hexagonal refactor relies on (clock injection, dead-code removal, dev posture).
- **PR-B is code-independent from PR-A** (touches `services.py`, `graph.py`, `storage/contracts.py`, `retrieval/contracts.py`, `frontend/src/**`, audit enums) but the stacked-to-main chain requires PR-A merged first. No file-level import between PR-A and PR-B.
- **PR-C is code-independent from PR-A and PR-B** (touches `app.py` lifespan/middleware, `schemas.py`, `auth.py`, frontend `main.tsx`/`App.tsx`, security/policy.py) but the stacked-to-main chain requires both PR-A and PR-B merged first. No file-level import between PR-C and the prior PRs except C.13 which extends B.18's redaction test surface.
- The order is enforced by **git branch ancestry** (PR-A -> PR-B -> PR-C each target `main`), not by Python/TS import dependencies. Reviewers can validate per-PR without reading the others.
- After all three PRs land, the archived `verify-report.md` should be re-run and the 4R reviewers (R1 Risk, R2 Readability, R3 Reliability, R4 Resilience) re-engaged for a zero-CRITICAL re-review.
