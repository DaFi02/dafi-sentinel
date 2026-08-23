# Design: Podman Containerization of Backend Dev/Test/Run (PR-A)

## Technical Approach

Extend the proven PR3 compose stack with a multi-stage Containerfile (base → sibling dep stages → `test`/`runtime` leaves). Rebuild-first ergonomics: the canonical test path rebuilds the `test` target so the suite runs lock-exact inside rootless Podman. Everything stays env-driven (`DAFI_PGVECTOR_SMOKE`, `DAFI_PGVECTOR_DSN`) — zero Python code changes. Verified ground truth: podman 5.8.4, podman-compose 1.6.0, SELinux Enforcing, uv 0.11.16, flat package layout (`dafi_sentinel/` at repo root), PEP 735 `[dependency-groups] dev`, `uv.lock` present, app object `dafi_sentinel.api.app:default_workbench_app`.

## Architecture Decisions

### D1 — Stage graph & image pins
Options: (A) one shared deps stage, (B) sibling prod/full dep stages. **Chosen: B** — `runtime` needs a `--no-dev` venv, `test` needs the dev group; one `.venv` path cannot serve both.

```dockerfile
ARG PYTHON_TAG=3.13-slim-bookworm            # pin by tag; digest upgrade documented
FROM docker.io/library/python:${PYTHON_TAG} AS base
# apt: ca-certificates only (psycopg[binary]/sklearn/numpy/matplotlib ship wheels)
# ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 · WORKDIR /app · useradd 10001:10001
FROM base AS deps-prod    # COPY pyproject.toml uv.lock → uv sync --frozen --no-dev --no-install-project
FROM base AS deps-full    # COPY pyproject.toml uv.lock → uv sync --frozen --no-install-project
FROM deps-full AS test    # COPY dafi_sentinel tests scripts → uv sync --frozen · USER 10001 · CMD pytest
FROM deps-prod AS runtime # COPY dafi_sentinel → uv sync --frozen --no-dev · USER 10001 · CMD uvicorn … ← LAST
```

`runtime` declared last so bare `podman build` yields the deployable image; `test` via `--target test`. Cache efficiency: manifests copied before source. uv binary via `COPY --from=ghcr.io/astral-sh/uv:<digest>`; digest captured at apply time from `uv:0.11` (docs cite the tag — proposal-resolved split). Upgrade: bump pin → rebuild both targets → suite green → promote. Base image: `python:3.13-slim-bookworm` tag pin.

### D2 — uv flags per target

| Target | Sync command | Rationale |
|---|---|---|
| deps-prod / runtime | `uv sync --frozen --no-dev` (two-phase, `--no-install-project` first) | prod-only; manifest layer cacheable |
| deps-full / test | `uv sync --frozen` | dev group: pytest, httpx, pytest-timeout |

`--frozen` forbids lock drift; any pyproject/lock edit invalidates dep stages by hash.

> **Correction (apply-time evidence):** `uv sync --frozen` does NOT fail on
> manifest/lock drift — it skips lock updates but still resolves. The shipped
> Containerfile uses `uv sync --locked`, which hard-fails when pyproject.toml
> and uv.lock disagree (verified by the Part A drift drill: requirement-level
> edits fail rc 1). Spec R2 wording was corrected accordingly.

### D3 — Non-root runtime & layout
UID/GID 10001 with home `/home/appuser`, created in `base`; `USER 10001` only in leaves (build steps stay root for `.venv` writes). `ENV PATH=/app/.venv/bin:$PATH`. Runtime CMD: `uvicorn dafi_sentinel.api.app:default_workbench_app --host 0.0.0.0 --port 8000` (existing PR5-documented invocation). Test CMD: `pytest -q` (config from copied `pyproject.toml`). Rejected: root-owned final image (violates rootless policy).

### D4 — Compose `api` service (additive, profile-gated)
Single compose file, `profiles: ["api"]` ⇒ plain `up -d` unchanged (postgres only); profiles + `depends_on.condition: service_healthy` are honored by installed podman-compose 1.6.0. **Fallback kept regardless**: `infra/podman/scripts/wait_for_postgres.py` is baked into images — reads `DAFI_PGVECTOR_DSN`, probes psycopg `SELECT 1` (1 s poll, `WAIT_TIMEOUT` default 60 s, stderr progress, exit 1 on timeout), then `os.execvp(sys.argv[1:])`; scoped to compose only via service-level `entrypoint:` override, so readiness never depends on compose feature gaps. Service keys: `build: {context: ../.., dockerfile: infra/podman/Containerfile, target: runtime}`, `ports: ["127.0.0.1:8000:8000"]` (loopback publish, rootless-safe >1024), `restart: unless-stopped`. No api healthcheck — no `/health` route exists (surface is auth-gated); manual `curl http://127.0.0.1:8000/docs` verification documented. Rejected: second compose file (split orchestration truth), host port 5432 (collision).

### D5 — Test execution flows
```sh
# infra-free default suite (contract preserved)
podman build --target test -t dafi-sentinel-test:local .
podman run --rm dafi-sentinel-test:local
# pgvector smoke — in-network DSN switch, env-only
podman network create dafi-sentinel-test-net
podman run -d --name sentinel-pg-smoke --network dafi-sentinel-test-net \
  -e POSTGRES_USER=sentinel -e POSTGRES_PASSWORD=sentinel -e POSTGRES_DB=sentinel \
  docker.io/pgvector/pgvector:pg16
podman run --rm --network dafi-sentinel-test-net \
  --entrypoint '["python","/opt/dafi/wait_for_postgres.py"]' \
  -e DAFI_PGVECTOR_SMOKE=1 \
  -e DAFI_PGVECTOR_DSN=postgresql://sentinel:sentinel@sentinel-pg-smoke:5432/sentinel \
  dafi-sentinel-test:local pytest tests/dafi_sentinel/test_pgvector_adapter.py -v
```
Composed variant: `podman-compose -f infra/podman/compose.yaml --profile api up -d`, DSN host `postgres` (service DNS, container port 5432 — not host-mapped 55432). Host-side flows keep `127.0.0.1:55432`. Default in-container suite stays infra-free: the smoke remains gated on `DAFI_PGVECTOR_SMOKE` (skip ⇒ exit 0).

### D6 — Mounts, SELinux, uv cache
Composed `api` mounts **nothing** (source baked). Optional fast loop (README-only): repo bind mount ro + `:Z` (SELinux Enforcing, single consumer) plus a **named volume** at `/app/.venv`; rejected: `:z` broad relabel, host `.venv` mounts (hard prohibition — denylisted and guarded). Build cache: `RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv` (buildah-native on podman 5.x); rejected persistent volume for build cache. `.containerignore` (denylist, matching proposal): `.git/`, `**/.venv/`, `.local/`, `**/__pycache__/`, `.pytest_cache/`, `node_modules/`, `frontend/`, `scripts/`, `openspec/`, `PORTFOLIO.md`.

### D7 — Guard tests (`tests/dafi_sentinel/test_container_workflow.py`)
No new markers — `--strict-markers` errors on unregistered marks; skips come from `pytestmark`/per-test `pytest.mark.skipif(shutil.which("podman") is None, reason="podman not available")` ⇒ podman-less CI stays green. `test_pr1_no_external_infra.py` untouched.
T0 (always-on, no podman): `.containerignore` denies `.venv`.
T1: `podman build --target runtime` rc 0 and `podman image inspect --format {{.Config.User}}` == `10001`.
T2: build `--target test`, run suite, assert rc == 0 — also catches pytest exit-5 empty-collection drift.
T3: `podman-compose -f infra/podman/compose.yaml config` renders rc 0.
Subprocess: `timeout=900` builds / `300` runs, `capture_output=True`.

### D8 — Branching & delivery (force-chained PRs; GitHub MCP publish, never local push)
Branch `podman-containerization/pr-a` from `main@3c26d5d`. **Gate**: the tree carries the unrelated HDFS-demo slice; it overlaps PR-A only on `README.md`. Before apply: land or stash the HDFS slice (minimally its README hunks); apply refuses to start with overlapping dirty paths.

| Unit | Content | Δ-line forecast | Rollback |
|---|---|---|---|
| U1 | Containerfile + .containerignore | ~90 | revert commit |
| U2 | compose `api` + wait_for_postgres.py | ~100 | revert commit |
| U3 | test_container_workflow.py (guards U1+U2) | ~90 | revert commit |
| U4 | README Podman workflow rewrite | ~60 | revert commit |

Total ≈ 340 ≤ 400 budget (incl. SDD docs); every unit well under — budget risk Low.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `infra/podman/Containerfile` | Create | 5-stage graph (D1/D2/D3), ~60 lines |
| `infra/podman/.containerignore` | Create | denylist context filter (D6) |
| `infra/podman/scripts/wait_for_postgres.py` | Create | DSN probe + execvp handoff, ~50 lines |
| `infra/podman/compose.yaml` | Modify (+~35) | additive profile-gated `api` service |
| `tests/dafi_sentinel/test_container_workflow.py` | Create | T0–T3 guards |
| `README.md` | Modify (~60) | all workflows as Podman commands |
| `dafi_sentinel/**`, `pyproject.toml` | None | untouched |

## Interfaces / Contracts

Env contract (names unchanged): `DAFI_PGVECTOR_SMOKE=1` opt-in; `DAFI_PGVECTOR_DSN` — in-network `postgresql://sentinel:sentinel@postgres:5432/sentinel`, host-side `postgresql://sentinel:sentinel@127.0.0.1:55432/sentinel`; new `WAIT_TIMEOUT` (probe seconds, default 60). Image contract: build targets `runtime|test`; local tags `dafi-sentinel-api:local`, `dafi-sentinel-test:local`; non-root `USER 10001`. Baked path `/opt/dafi/wait_for_postgres.py`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Static | `.venv` exclusion holds | T0, runs on any host |
| Integration | both targets build; non-root; suite passes in-container | T1/T2 via podman, auto-skipped without it |
| E2E | pgvector adapter vs live pg16 | existing `DAFI_PGVECTOR_SMOKE` path, in-network DSN (D5) |

## Migration / Rollout

No migration, no production modules touched. Additive profile-gated compose ⇒ PR3 flow cannot regress. Per-unit rollback: `git revert` each unit commit; whole-change: delete new files + revert compose/README hunks (proposal plan).

## Open Questions

- [ ] Confirm the pending HDFS-demo slice lands (or stashes) before apply — blocking gate for U4 (README overlap).
