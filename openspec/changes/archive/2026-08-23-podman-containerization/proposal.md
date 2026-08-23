# Proposal: Podman Containerization of Backend Dev/Test/Run (PR-A)

Change: `podman-containerization` · Store: hybrid · Date: 2026-08-22

## Intent

All backend workflows (dev shell, pytest, pgvector service, API server) run on the host via `uv`/`.venv`, violating the new Podman-first policy: **everything** must run in Podman 5.8.4 rootless containers. Why now: the policy is active, rootless podman-compose is already proven here (PR3 pgvector stack), and the frontend slice (PR-B) is blocked behind a containerized backend. Measurable outcome: every documented backend workflow executes via Podman with zero host venv usage.

## Scope

### In Scope
- `infra/podman/Containerfile` (new): multi-stage `python:3.13-slim` + pinned uv (`COPY --from=ghcr.io/astral-sh/uv:<digest>`); targets `runtime` (`uv sync --frozen --no-dev`) and `test` (`--frozen`, dev group included). No apt packages expected (psycopg[binary] bundles libpq; sklearn/numpy/matplotlib ship wheels).
- `infra/podman/.containerignore` (new): excludes `.venv`, `.git`, `.local/`, `node_modules`, caches. Host `.venv` must NEVER enter an image or bind mount.
- `infra/podman/compose.yaml` (modify, additive): profile-gated `api` build service on `127.0.0.1:8000`; existing `postgres` service untouched.
- Pytest via the `test` target; pgvector smoke in-network using `postgresql://sentinel:sentinel@postgres:5432/sentinel` (env-driven, no code change).
- `README.md` run/test sections rewritten around Podman commands (rootless-safe: ports >1024, SELinux `:z/:Z` labels).
- Guard tests proving: default suite still runs infra-free; container targets build and pass.

### Out of Scope
- Frontend containerization (Node image, env-configurable Vite proxy, vitest-in-container) → chained PR-B.
- Production deploy surface (`dafi_sentinel/deploy|telemetry` remain forbidden).
- Task-runner wrapper (Makefile/scripts) — README-only documentation.

## Capabilities

### New Capabilities
- `containerized-backend-workflow`: rootless-Podman requirements for building runtime/test images, extending the compose stack, and running tests/API containers without breaking the infra-free default pytest contract.

### Modified Capabilities
None — no requirement-level behavior changes to existing specs (`rag-document-retrieval`, `investigation-workbench`, etc.).

## Approach

Extend, not greenfield: the PR3 compose stack stays the single source of orchestration. Canonical test path = rebuild `test` target (reproducible, lock-exact); bind-mounted source with `:z` + named-volume `.venv` documented as optional fast loop. Layer order: manifest+lock copied before source; cache mount for uv.

**Open decisions (resolved)**: single compose file with profiles (continuity, fewer lines); rebuild-first ergonomics (reproducibility value); README-only docs (no runner convention exists); uv pinned by digest in builds, tag in docs.

## Affected Areas

| Area | Impact |
|---|---|
| `infra/podman/Containerfile` | New |
| `infra/podman/.containerignore` | New |
| `infra/podman/compose.yaml` | Modified (+~35 lines, profile-gated) |
| `README.md` | Modified (~50–80 lines) |
| `tests/dafi_sentinel/test_container_workflow.py` | New guard/smoke (~60–90) |
| `dafi_sentinel/**` | Unchanged |

## Risks

| Risk | Sev | Mitigation |
|---|---|---|
| podman-compose gaps (`depends_on: condition`, profiles) | Med | Verify in apply; wait-for-postgres fallback documented |
| Dirty working tree (uncommitted HDFS demo slice) | Med | Implementation branches from clean HEAD; unrelated work excluded |
| First-build time/size (ML wheels) | Med | Layer order + uv cache mount proven during apply |
| SELinux relabel cost (`:z` on repo bind) | Low | Prefer `:Z`; named volumes where possible |
| `--reload` inotify over bind mounts; demo corpus absent in-container | Low | Documented host-side alternatives |

## Delivery & Review Budget (force-chained PRs)

- PR-A (this change): forecast **~250–330 changed lines** incl. SDD docs. Decision needed before apply: No. Chained PRs recommended: Yes (PR-B frontend follow-up). 400-line budget risk: Low.
- PR-B: separate change for frontend containerization.

## Rollback Plan

Delete new files (Containerfile, .containerignore, guard tests); revert compose/README hunks. Compose change is additive and profile-gated, so the PR3 smoke flow never regresses. No migrations, no production code touched.

## Dependencies

Podman 5.8.4 rootless + podman-compose provider (installed, proven); registry pulls: `python:3.13-slim`, `ghcr.io/astral-sh/uv`, `pgvector/pgvector:pg16` (already cached locally).

## Acceptance Criteria

- [ ] Both image targets build rootlessly; no host `.venv` baked or mounted.
- [ ] Full suite passes inside `test` target; host default run still requires no Podman (guard intact).
- [ ] Profile-gated `api` serves 127.0.0.1:8000 beside postgres; plain `up -d` behavior unchanged.
- [ ] README documents all workflows as Podman commands.
- [ ] Diff within 400-line budget; branch starts from clean HEAD.

## Proposal question round

Executor ran non-interactively; decision gaps were pre-resolved by orchestrator directives (see explore.md §Open decisions). Flag corrections before the spec phase.
