# Exploration: Podman containerization of dafi_sentinel

Change: `podman-containerization` · Store: hybrid (this file + Engram `sdd/podman-containerization/explore`) · Date: 2026-08-22

## Current State

### Backend dev / test / run (all on host today)

| Concern | Command / file | Evidence |
|---|---|---|
| Env setup | `uv sync` → host `.venv`, Python 3.13 | `.python-version` (`3.13`), uv 0.11.16 on host, `.venv/` present, `uv.lock` committed (~322 KB) |
| Default tests | `uv run pytest` | `pyproject.toml`: `testpaths = ["tests/dafi_sentinel"]`, strict markers/config, no cacheprovider |
| pgvector smoke | `DAFI_PGVECTOR_SMOKE=1 DAFI_PGVECTOR_DSN=postgresql://sentinel:sentinel@127.0.0.1:55432/sentinel uv run pytest tests/dafi_sentinel/test_pgvector_adapter.py -v` | README "Run the pgvector smoke (PR3)"; env-gated `skipif` in the test module |
| pgvector service | `podman compose -f infra/podman/compose.yaml up -d` / `down -v` | **`infra/podman/compose.yaml` EXISTS** — `docker.io/pgvector/pgvector:pg16`, port `127.0.0.1:55432→5432`, named volume `dafi-sentinel-pgdata`, `pg_isready` healthcheck, creds sentinel/sentinel |
| API server | `uv run uvicorn dafi_sentinel.api.app:default_workbench_app --reload` (port 8000) | README PR5 section; dev factory refuses to boot when `DAFI_PRODUCTION_POSTURE=1`; prints random seeded-user passwords to log unless `DAFI_DEV_PASSWORD` is set |
| Demo corpus script | `uv run python scripts/prepare_hdfs_v1_demo.py --acknowledge-loghub-terms` | Only file in `scripts/`; writes gitignored `.local/hdfs-v1/`, served via `DAFI_HDFS_DEMO_PATH` |
| Frontend tooling | `npm run dev` (vite :5173), `build` (`tsc --noEmit && vite build`), `test` (vitest) | `frontend/package.json`; `frontend/vite.config.ts` proxies `/sessions /evidence /qa /charts /roles /audits` → hardcoded `http://127.0.0.1:8000` |

### Host facts (verified live)

- Fedora 44, **SELinux Enforcing**, Podman 5.8.4 **rootless**, amd64.
- `podman compose` works and delegates to external provider `~/.local/bin/podman-compose` — already proven by the PR3 smoke workflow.

### Corrections to orchestrator context

- "Repo has NO compose files" is **stale**: `infra/podman/compose.yaml` was delivered in PR3 and is referenced by README, `openspec/config.yaml` (testing commands), and guard test `test_pr1_no_external_infra.py` (asserts `infra/podman/` exists). This change must **extend** the existing stack, not create it.
- No Containerfile/Dockerfile exists anywhere (glob-verified). That part of the context holds.

### Constraints discovered in code

- `test_pr1_no_external_infra.py`: default pytest run MUST NOT require Postgres/Podman; forbidden paths include `dafi_sentinel/deploy` and `dafi_sentinel/telemetry`. Container assets belong under `infra/` (already a permitted, required location).
- The smoke test's DSN is a host-loopback address; inside a compose network it must become `postgresql://sentinel:sentinel@postgres:5432/sentinel` (env-driven, so no code change needed — only invocation differs).
- Working tree is currently **dirty** with an uncommitted HDFS-demo slice (untracked `scripts/`, `dafi_sentinel/ingestion/hdfs_v1.py`, etc.). Containerization work should branch from clean HEAD.

## Affected Areas

- `infra/podman/Containerfile` (new) — multi-stage backend image (runtime + test targets).
- `infra/podman/.containerignore` (new) — exclude `.venv`, `.git`, `.local/`, `node_modules`, `__pycache__`.
- `infra/podman/compose.yaml` (modify) — add `api` service behind a profile; keep `postgres` as-is for the existing smoke flow.
- `README.md` (modify) — replace/augment host-only quick start with Podman equivalents.
- `openspec/config.yaml` (possible modify at archive time) — testing layer notes once tests can run in-container.
- `frontend/vite.config.ts` (only if frontend slice proceeds) — proxy target must become configurable for container networking.
- No production code under `dafi_sentinel/` needs changes (env-driven config everywhere).

## Approaches

### A1. Base image strategy

| Option | Pros | Cons | Effort |
|---|---|---|---|
| `python:3.13-slim` + `COPY --from=ghcr.io/astral-sh/uv:<pinned>` | Pin uv by tag/digest; slim final image; Astral-documented pattern; full control of stages | Two extra lines vs dedicated image; cache dir management is ours | Low |
| `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` as builder only | Zero manual uv install; maintained combo tag | Couples builder to Astral tag cadence; Debian suite drift (bookworm vs trixie); still needs multi-stage for slim runtime | Low |
| `python:3.13-slim` + `pip install uv` | Simplest | Unpinned tool in-image; extra pip layering; slowest path | Low |

**Recommendation: Option 1** — pin uv explicitly (reproducibility is a stated project value), build wheels are manylinux so **no compiler/libpq system packages needed** (`psycopg[binary]` bundles libpq; scikit-learn/numpy/matplotlib ship wheels) — keep apt out of the image unless apply proves otherwise.

### A2. Compose orchestration

| Option | Pros | Cons | Effort |
|---|---|---|---|
| Extend `podman compose` stack (existing podman-compose provider) | Already installed & proven here (PR3 smoke); declarative healthchecks; one mental model; README continuity | podman-compose lags docker-compose v2 on some flags (`depends_on: condition:` support historically partial — verify during apply) | Low |
| Raw `podman run`/`podman play kube` scripts | Max control; no provider dependency | Re-implements what compose.yaml already does; more script lines against 400-line budget; harder teardown | Medium |

**Recommendation: extend the existing compose file** — add an `api` service (build context repo root or `infra/podman`) behind a compose profile so plain `up -d` (smoke flow) is unchanged; document fallback wait-for-postgres loop if `condition: service_healthy` proves flaky under podman-compose.

### A3. Test execution

| Option | Pros | Cons | Effort |
|---|---|---|---|
| Multi-stage `test` target (dev group baked via `uv sync --frozen`), `podman run <target> uv run pytest` | Reproducible, lock-exact; image layers cached; runtime stage stays lean (no dev deps) | Requires rebuild for dependency changes | Low |
| Bind-mount source into runtime image + ephemeral pytest | Fast iteration, no rebuild per edit | Needs SELinux `:z` relabel; host `.venv` must NEVER be mounted (Linux venvs are non-relocatable; symlinked uv python breaks inside container) — use a named volume for container-side `.venv` if bind-mounting | Medium |

**Recommendation: both, layered** — canonical path is the `test` target (used by verify/CI); optional bind-mount variant documented for fast inner loops. Never bake or mount host `.venv`.

### A4. Rootless Podman gotchas (Fedora-specific, verified Enforcing)

- Ports: all planned ports >1024 (8000 api, 5173 vite, 55432 postgres) — rootless-safe; 55432 binding already proven.
- SELinux: any source bind mount **must** carry `:z` (shared) or `:Z` (private); named volumes need no labels. Prefer `:Z` for single-container mounts; recursive relabel of a large tree has a one-time cost.
- UID mapping: container-root = host `dafi`; files created by containers in bind mounts appear owned by `dafi` — safe here since the repo is already owned by `dafi`.
- uv cache: set `UV_CACHE_DIR` and persist via BuildKit-style cache mount (`podman build` supports `--mount=type=cache`) or accept layer-cache-only builds.
- `--reload` uvicorn relies on inotify over the bind mount — works with `:z` but re-check during apply.
- Dev factory prints credentials to stdout → `podman logs` becomes a credential surface (dev-only, acceptable; `DAFI_DEV_PASSWORD` covers scripted runs).

### A5. uv.lock in container builds

- Copy `pyproject.toml` + `uv.lock` **before** source for layer caching; `uv sync --frozen --no-dev` for the runtime stage and `--frozen` (+ dev group) for the test target. `--locked` (asserts lock freshness) belongs in CI, not necessarily in every local build.

## Scope decision: frontend

**Out of this slice — chain it.** Rationale:
1. Backend slice alone lands ~250–330 changed lines (Containerfile ~70, .containerignore ~15, compose +~35, README ~50–80, container smoke/guard tests ~60–90, plus SDD planning docs) — near budget already.
2. Frontend needs its own Node multi-stage image, an env-configurable Vite proxy (hardcoded `127.0.0.1:8000` breaks cross-container DNS), and vitest-in-container decisions — a coherent second link, mirroring how PR3 (infra) and PR5 (frontend) were split before.

## Recommendation

Multi-stage `python:3.13-slim` + pinned uv image under `infra/podman/Containerfile` (targets: `runtime`, `test`), extend the existing compose stack with a profile-gated `api` service, run pytest via the `test` target, keep frontend for a chained follow-up PR. All assets under `infra/` to respect the `test_pr1_no_external_infra.py` boundary guards.

## Risks

| Severity | Risk |
|---|---|
| HIGH | Orchestrator context stale re: compose file — proposing "create" instead of "extend" would collide with PR3 artifacts and guard tests (mitigated: verified above). |
| MEDIUM | podman-compose feature gaps (`depends_on: condition: service_healthy`, profiles) may require wait-loop fallback in the smoke path. |
| MEDIUM | Dirty working tree (uncommitted HDFS demo slice) — branch hygiene required to avoid mixing concerns in the PR. |
| MEDIUM | Image size / first-build time driven by scikit-learn + matplotlib + numpy wheels; mitigations (layer order, cache mount) must be proven in apply. |
| LOW | SELinux relabel cost and label side effects on bind-mounted repo (`:z`). |
| LOW | uvicorn `--reload` inotify behavior over overlayfs/bind mounts. |
| LOW | HDFS demo data (`.local/hdfs-v1/`) unavailable in-container unless bind-mounted — demo flow should stay documented as host-side or explicitly mounted. |
| LOW | Guard-test boundary (`dafi_sentinel/deploy|telemetry` forbidden) — satisfied by placing everything under `infra/`, but proposal must state it. |

## Open decisions for the proposal

1. Compose layout: profile-gated `api` in the single existing compose.yaml (recommended) vs separate dev/smoke files.
2. Dev iteration ergonomics: bind-mount-with-`:z` documented as primary vs rebuild-per-change (canonical) — recommend canonical-first, bind-mount as documented option.
3. Whether to add a thin task wrapper (Makefile/scripts) or README-only documentation — recommend README-only given zero current task-runner convention and line budget.
4. Exact uv pin mechanism: version tag vs digest (recommend digest for builds, tag in docs).

## Ready for Proposal

Yes. Proposal phase should: (a) treat infra/podman/compose.yaml as existing surface to extend, (b) plan chained PR-A backend / PR-B frontend, (c) forecast line counts against the 400-line budget including SDD planning docs, (d) define rollback (delete new files; compose change is additive/profile-gated).
