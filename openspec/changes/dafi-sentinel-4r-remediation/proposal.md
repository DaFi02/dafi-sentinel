# Proposal: DAFI Sentinel 4R Remediation

> **Change name**: `dafi-sentinel-4r-remediation`
> **Trigger**: Post-archive 4R review of merged `dafi-sentinel` (PR #1, commit `459e586`).
> **Reviewers**: R1 Risk, R2 Readability, R3 Reliability, R4 Resilience. 11 CRITICAL, 27 HIGH, 71 MEDIUM, 73 LOW/INFO findings. Full reports in Engram observations `#603`, `#604`, `#601`, `#602`. The archived `verify-report.md` already documents 11 SUGGESTIONs and 5 WARNINGs — this change addresses them.

## Intent

Harden the shipped `dafi-sentinel` change against the residual production-readiness, determinism, hexagonal-architecture, and dead-code gaps surfaced by the post-merge 4R review. Deliver a stacked PR chain that fits the 400-line review budget where possible and uses the precedent's `size:exception` flag for the larger cleanup slices, with no spec-level behavior change.

## Scope

### In Scope

- **All 11 CRITICAL findings** (R1 high#1-#5, R2 crit#1-#7, R3 F1-F3, R4 crit#1-#4).
- **All 27 HIGH findings** (R1 high#1-#5, R2 high#1-#11, R3 F4-F8, R4 high#1-#7).
- **Selected MEDIUM/LOW**: redaction regex expansion (R1 med#11), `inspect_user_request` parametrization (R3 F11), `ML` edge cases (R3 F12), chart-renderer edge cases (R3 F13), `LoginPage` default credentials removal (R2 med), pgvector SQL-injection f-string (R2 med), cookie+Bearer collision (R1 med), session_id hash (R3 F18), frontend error-render dedup (R2 high#5), `DAFI_DEV_NO_CSP_META` implementation (R2 high#7), `RolesPage` setState fix (R3 F4), magic-string audit enums (R2 high#3), `enabled` parameter removal (R2 high#6).
- **Selected LOW/INFO**: case-insensitive auth test pin (R3 F23), synchronous ResizeObserver stub (R3 F29), `_records_for` drop diagnostic (R3 F21), logout cookie split-assertions (R3 F14), login-error leak test (R3 F26), pgvector timeout test (R3 F15).

### Out of Scope

- New product features.
- New OpenSpec specs or delta specs — this is a hardening change that strengthens existing scenarios; no requirement changes.
- Real Postgres-backed stores (deferred to a deployment slice; in-memory + opt-in pgvector smoke remain the contract).
- Multi-tenant RBAC, enterprise SSO, fine-tuned models, cloud/SIEM integrations, Grafana/Prometheus.
- Sweeper-pgvector coupling (sweeper stays in-process; pgvector stays per-query).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. All 24 archived spec scenarios must remain COMPLIANT; this change strengthens implementation, not requirements.

## Approach

Three stacked PRs against `main`, each independently addressable. The chain is `PR-A → PR-B → PR-C`, all stacked-to-main per the 4R review's chained-PR recommendation.

| PR | Title | Budget | Strategy | Anchors |
|---|---|---:|---|---|
| **PR-A** | Hotfix CRITICAL | ≤400 lines | fits budget | R3 F1+F2+F3, R1 high#1, R2 crit#1-#4, R4 crit#1, R4 high#1 |
| **PR-B** | Hexagonal cleanup | ~700 lines | `size:exception` (precedent PR3-PR6) | R2 crit#5-#7, R2 high#1-#4, R2 high#7, R3 F4-F8, R3 F18-F19 |
| **PR-C** | Production-readiness | ~900 lines | `size:exception` (precedent) | R1 high#2-#5, R1 med#8/#9/#11, R4 crit#2-#4, R4 high#2-#7 |

**PR-A — Hotfix CRITICAL (≤400 lines).** Delete 4 dead-code symbols (`EvidenceRepositoryAdapter`, `RecentEvidenceCache`, `base64_to_png`, `useMe`/`useLogin`/`useLogout`). Add `forbidOnly` to `pyproject.toml` and `vite.config.ts`. Inject clock into `_build_audit_record` (graph.py:560) and `WorkbenchService._record_audit` (services.py:309) and write `test_orchestration_audit_timestamps_are_deterministic_with_injected_clock`. Add `app.exception_handler(ChartValidationError)` returning 422 + parametrized chart-validation tests for empty `evidence_ids`, blank `evidence_id`, blank `x`. Remove the plaintext `hunter2!` seeded password from `README.md:112-113` and `app.py:386`; replace with dev-only random-on-boot or env-var override. Mark `default_workbench_app` as dev-only posture in code and README.

**PR-B — Hexagonal cleanup (~700 lines, size:exception).** Widen `WorkbenchService.evidence` to `EvidenceRepository` Protocol (services.py:144). Inject `RetrievalIndex` into `WorkbenchService` instead of always building a fresh `InMemoryRetrievalIndex` (services.py:148-149). Honor `session_id` in `InMemoryAuditRepository.write_audit` (services.py:93-95). Extract `AuditAction` / `AuditReason` enums and replace the 11 magic strings across 5 files. Refactor the 91-line, 4-return-path approval node (graph.py:300-389). Delete the legacy `approver_id` fallback in `_coerce_approval` (graph.py:519-525). Fix `setState` in render in `RolesPage.tsx:9-13` via `useEffect`. Remove the dead `enabled` parameter from frontend mutations. Implement or remove `DAFI_DEV_NO_CSP_META`. Move `_SYSTEM_APPROVER` declaration before its first reference (graph.py:606-610). Add `test_orchestration_system_approver_passes_authorization_check`. Add audit-timestamp determinism + sweeper clock injection (R3 F2, R3 F6).

**PR-C — Production-readiness (~900 lines, size:exception).** Add a `production_graph()` factory example that uses `PostgresSaver` (gated on env var) — in-memory stays the default. Mount `sweep_stale_pauses` as a FastAPI lifespan background task with proper shutdown. Add security middleware: `CORSMiddleware`, `TrustedHostMiddleware`, `HTTPSRedirectMiddleware`, HSTS, `Cache-Control: no-store` on `/sessions` and `/audits`. Add rate limits + payload-size caps on `/sessions`, `/qa`, `/charts`. Add server-side approver lookup so `_evaluate_approver` (graph.py:530-544) trusts the user store, not caller-supplied `UserRef`. React `ErrorBoundary` with retry on top of `<App>` plus `QueryClient` `retry:1`. Add `logging.basicConfig` setup and `request_id` middleware. Add `threading.RLock` to `InMemoryEvidenceRepository` and `InMemoryAuditRepository` (services.py:46-103, 142-146). Implement `DAFI_DEV_NO_CSP_META` (R2 high#7, picked up from PR-B if not done). Add CORS allow-list, session-id hash for login audit (R3 F18), expand redaction regex to cover `aws_*`, `github_pat_*`, JWT, generic `api_key=`. Add the parametrized redaction / `inspect_user_request` / ML / chart-renderer edge-case tests (R3 F10-F13).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `dafi_sentinel/api/app.py` | Modified | Add `ChartValidationError` handler, lifespan, security middleware, rate limits, remove plaintext seeded password, mark `default_workbench_app` dev-only. |
| `dafi_sentinel/api/services.py` | Modified | Delete `EvidenceRepositoryAdapter`/`RecentEvidenceCache`/`base64_to_png`; widen `evidence` to `EvidenceRepository`; inject `RetrievalIndex` and `clock`; honor `session_id`; add `RLock`; remove magic strings. |
| `dafi_sentinel/api/auth.py` | Modified | Session-id hashing; dev-only cookie posture markers. |
| `dafi_sentinel/api/schemas.py` | Modified | `LoginRequest.password` and `QuestionRequest.question` `max_length`; allow-list for chart fields. |
| `dafi_sentinel/orchestration/graph.py` | Modified | Clock injection; refactor approval node; delete legacy `approver_id` fallback; reorder `_SYSTEM_APPROVER`; add system-approver test. |
| `dafi_sentinel/retrieval/contracts.py` | Modified | `InMemoryRetrievalIndex` ranking contract documented (R3 F24). |
| `dafi_sentinel/security/policy.py` | Modified | Expand redaction regex; parametrize `inspect_user_request` triggers. |
| `dafi_sentinel/charts/validation.py` | Modified | Reject empty/blank `evidence_ids` and blank `x`/`y` at the validator level. |
| `dafi_sentinel/storage/contracts.py` | Modified | `@runtime_checkable` on `AuditRepository`/`EvidenceRepository` (asymmetry fix). |
| `frontend/src/api/queries.ts` | Modified | Delete `useMe`/`useLogin`/`useLogout`; remove `enabled` from mutations. |
| `frontend/src/pages/RolesPage.tsx` | Modified | `useEffect`-based `setUserId` from session. |
| `frontend/src/main.tsx`, `frontend/src/App.tsx` | Modified | Mount `ErrorBoundary`; bump `QueryClient` retry to 1; implement `DAFI_DEV_NO_CSP_META`. |
| `pyproject.toml` | Modified | `addopts` for `forbidOnly`, strict markers, no cache provider. |
| `frontend/vite.config.ts` | Modified | `forbidOnly: true`; add `test.timeout` for slow Vitest. |
| `tests/dafi_sentinel/test_*.py` | Modified | New tests: clock-determinism, system-approver authz, chart-validation params, sweeper clock, ingestion edges, redaction params, ML edges, chart edges, logout split-assertions, pgvector timeout. |
| `frontend/src/test/*.test.{ts,tsx}` | Modified | New tests: ErrorBoundary fallback, RolesPage re-render, `DAFI_DEV_NO_CSP_META` toggle, auth error-pin. |
| `README.md` | Modified | Remove plaintext `hunter2!`; mark `default_workbench_app` as dev-only; document hardened posture. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Hexagonal refactor (`evidence` widening, `RetrievalIndex` injection) breaks existing tests | Medium | TDD per task: red/green captured in Engram; keep `InMemoryEvidenceRepository` and `InMemoryRetrievalIndex` as Protocol implementations; no behavior change at the call site. |
| `ChartValidationError` handler regresses existing chart tests | Medium | Add the handler BEFORE relaxing the catch-all; add parametrized `test_charts_endpoint_rejects_invalid_spec` cases (empty `evidence_ids`, blank id, blank `x`); run full pytest before merge. |
| `WorkbenchService` port widening breaks `_SYSTEM_APPROVER` path | Low | Port widening is structural, not behavioral; existing 4 PR6 tests must pass unchanged. |
| PR-B and PR-C each exceed 400 lines | High (expected) | Marked `size:exception` in tasks.md; precedent: PR3-PR6 in the archived change. Per-PR 4R review before merge. |
| Security middleware changes break the local dev server | Medium | `default_workbench_app` keeps `cookie_secure=False` and skips `HTTPSRedirect`; middleware only active in the production-graph factory example. |
| Sweeper as background task leaks threads across reloads | Low | Use `asyncio.create_task` in FastAPI lifespan with explicit cancellation on shutdown; unit test the lifespan context. |
| Frontend `ErrorBoundary` swallows real bugs | Low | Boundary logs the error and shows a retry button; non-recoverable boundary hits go to a visible banner; existing test surface unchanged. |
| `threading.RLock` regresses single-process performance | Low | Lock scope limited to `_records` / `_owners` mutations; reads remain lock-free. |

## Rollback Plan

Per-PR revert on `main` (not per-change — this is a single change delivered in three stacked PRs). PR-A revert is non-destructive (dead-code deletion + small handlers). PR-B revert restores the concrete-typed `WorkbenchService`; no schema change. PR-C revert removes the production factory, middleware, and lifespan task without touching existing endpoints. Each PR is a single revert commit; no database migration is introduced.

## Dependencies

None new. Reuses `uv`, `pytest`, `fastapi`, `langgraph`, `pydantic`, `passlib[argon2]`, `starlette` middleware, `vitest`, `@tanstack/react-query`. No new transitive deps.

## Success Criteria

- [ ] All 11 CRITICAL findings remediated (R1 high#1-#5, R2 crit#1-#7, R3 F1-F3, R4 crit#1-#4).
- [ ] All 27 HIGH findings remediated.
- [ ] All 24 archived spec scenarios remain COMPLIANT (no regression).
- [ ] `uv run pytest` passes — baseline 104 + ≥30 new tests across PR-A/B/C.
- [ ] `npm test` passes — baseline 15 + ≥6 new frontend tests.
- [ ] `tsc --noEmit` clean; `vite build` clean.
- [ ] PR-A fits 400-line review budget without `size:exception`.
- [ ] PR-B and PR-C are explicitly flagged `size:exception` with rationale referencing the archived PR3-PR6 precedent.
- [ ] No new OpenSpec specs introduced; no delta specs required.
- [ ] Per-PR 4R review: R1+R2+R3+R4 each emit 0 CRITICAL after the chain merges.
