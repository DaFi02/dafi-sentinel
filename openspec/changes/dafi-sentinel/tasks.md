# Tasks: DAFI Sentinel

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1,900-2,800 total; PR1 391 after trim |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 foundation/auth contracts -> PR2 ingestion/security policy -> PR3 pgvector -> PR4 ML/charts -> PR5 API/dashboard/auth -> PR6 LangGraph |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

## PR1 Plan: Foundation Only

- [x] 1.1 Add pytest via `uv add --dev pytest`; verify `uv sync` and `uv run pytest`.
- [x] 1.2 Create importable skeletons: `dafi_sentinel/__init__.py`, `domain/`, `retrieval/`, `storage/`.
- [x] 1.3 Create `dafi_sentinel/domain/models.py` dataclass contracts: incidents, evidence, documents, `ActorRef`, `UserRef`, `Role`, `Permission`, policy decisions, chart specs, audits.
- [x] 1.4 Create `dafi_sentinel/retrieval/contracts.py` with `RetrievalIndex` protocol and fixture/in-memory hooks only.
- [x] 1.5 Create `dafi_sentinel/storage/contracts.py` repository protocols for evidence, timeline, and actor-attributed audit writes.
- [x] 1.6 Add minimal in-test fixture data for valid incident, runbook/document retrieval, and policy/audit contracts; defer standalone fixture corpus to PR2.
- [x] 1.7 Add `tests/dafi_sentinel/test_foundation_contracts.py` for evidence IDs, source metadata, actor audit fields, role/permission shape, chart specs, fixture retrieval.
- [x] 1.8 Add `tests/dafi_sentinel/test_pr1_no_external_infra.py` proving no PostgreSQL, pgvector, Podman, Grafana, Prometheus, LangGraph, login, tokens, or SSO are required.
- [x] 1.9 Update `README.md` with the minimal `uv sync` and `uv run pytest` path; mark pgvector/auth implementation as later work.
- [x] 1.10 PR1 acceptance: tests pass; changed lines stay under 400 after trimming standalone fixtures/export boilerplate; no DB, frontend, auth middleware, or orchestration implementation.

## Later Slices

- [x] 2.1 PR2 add RED/GREEN ingestion tests/services for valid datasets, malformed rollback, traceability, redaction handoff.
- [x] 2.1a PR2 add standalone valid incident, malformed row, runbook/document, and prompt-injection fixtures removed from PR1 to stay under review budget.
- [x] 2.2 PR2 add RED/GREEN security tests/services for injection-as-data, policy refusal, redaction, role-based tool authorization, approvals, audits.
- [x] 3.1 PR3 add `uv add psycopg[binary] pgvector`, `infra/podman/compose.yaml`, docs, and pgvector adapter smoke.
- [x] 4.1 PR4 add `uv add scikit-learn numpy`, deterministic analysis, chart validation, and controlled matplotlib renderer.
- [ ] 5.1 PR5 add FastAPI auth/session middleware and endpoints for owned sessions, evidence, Q&A, charts, roles, audits.
- [ ] 5.2 PR5 add React + TypeScript + Vite dashboard with authenticated ownership, TanStack Query, and Recharts.
- [ ] 6.1 PR6 add scoped LangGraph orchestration; approvals must pause execution.
