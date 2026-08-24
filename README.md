# DAFI Sentinel

DAFI Sentinel is a security-first incident investigation workbench.

For a concise explanation of the product, its investigation flow, technical decisions, and honest AI-assisted portfolio framing, see [PORTFOLIO.md](PORTFOLIO.md).

## Quick start

All backend workflows run in rootless Podman containers. Build both
images and run the suite lock-exact inside the test image:

```bash
podman build -f infra/podman/Containerfile --target runtime -t dafi-sentinel-api:local .
podman build -f infra/podman/Containerfile --target test -t dafi-sentinel-test:local .
podman run --rm dafi-sentinel-test:local
```

Dependencies sync with `uv sync --locked` inside the image — the build
fails on manifest/lock drift, so images always match `uv.lock`. The
default pytest run inside the container needs no live database,
external service, or host Python setup. Container guard tests
(`tests/dafi_sentinel/test_container_workflow.py`) skip cleanly on hosts
without `podman`, so CI stays green either way.

### Container workflow reference

| Concern | Rule |
|---|---|
| Ports | Loopback publish only, >1024 (`127.0.0.1:8000`, `127.0.0.1:55432`) |
| Host `.venv` | NEVER mounted or baked — images sync lock-exact via `uv sync --locked` |
| Optional fast loop | Read-only bind mount labeled `:Z` (SELinux) + named volume at `/app/.venv` |
| Env contract | `DAFI_PGVECTOR_SMOKE` · `DAFI_PGVECTOR_DSN` · `WAIT_TIMEOUT` (default 60 s) |
| Rebuild gotcha | Compose reuses its own `<project>_api` image across ups — find it with `podman images \| grep api` and `podman rmi` it after manual target rebuilds |

## Local-only HDFS_v1 demo

This optional demo makes locally prepared [LogHub HDFS_v1](https://github.com/logpai/loghub/tree/master/HDFS) operational-benchmark evidence visible in the workbench. It is not a cybersecurity-incident corpus: `Normal` and `Anomaly` are source benchmark metadata, **not cybersecurity attack conclusions**.

### Reproducible reviewer walkthrough

1. Review the [LogHub license](https://github.com/logpai/loghub/blob/master/LICENSE), the [HDFS_v1 documentation](https://github.com/logpai/loghub/tree/master/HDFS), and the [pinned Zenodo record](https://zenodo.org/records/8196385). The official artifact is `https://zenodo.org/api/records/8196385/files/HDFS_v1.zip/content` (DOI `10.5281/zenodo.8196385`).
2. Prepare the corpus only after accepting those terms:

   ```bash
   uv run python scripts/prepare_hdfs_v1_demo.py --acknowledge-loghub-terms
   ```

   The command validates the published `md5:76a24b4d9a6164d543fb275f89773260`, deterministically writes `.local/hdfs-v1/output/normalized.jsonl`, and fails before download when the acknowledgement is absent. No official SHA-256 is published for this artifact; the project does not claim one.
3. Start the development API with that prepared local file explicitly enabled:

   ```bash
   export DAFI_HDFS_DEMO_PATH="$PWD/.local/hdfs-v1/output/normalized.jsonl"
   uv run uvicorn dafi_sentinel.api.app:default_workbench_app --reload
   ```

   Start the dashboard as described below, sign in with the development credential printed by the API, open an HDFS evidence item, and inspect its detail view. The API `GET /evidence/{id}` and the dashboard provenance panel show the source URI, version/checksum reference, trace ID, benchmark label, and the operational-benchmark disclaimer.

### Provenance and distribution boundary

| Topic | Evidence / boundary |
|---|---|
| Attribution | LogHub HDFS_v1; cite Xu et al. (SOSP 2009) and Zhu et al. (LogHub, ISSRE 2023) as requested by the official HDFS documentation. |
| Terms | LogHub makes datasets available for research or academic work and requires its notice and citation where applicable; preparation requires explicit acknowledgement. |
| Integrity | The pinned Zenodo record publishes the MD5 above. No official SHA-256 is published. |
| Corpus handling | Raw archive, cache, and normalized JSONL stay under ignored `.local/hdfs-v1/`; they are **not committed or redistributed**. No starter subset is shipped. |
| Labels | `Normal` / `Anomaly` remain operational benchmark metadata, not cybersecurity attack conclusions. |

The repository intentionally does not resolve the ambiguous permission for a normalized derivative. To roll back the optional demo, unset `DAFI_HDFS_DEMO_PATH` and delete `.local/hdfs-v1/`; default API startup remains unseeded.

## Run the pgvector smoke (PR3)

The pgvector retrieval adapter has an opt-in smoke test that requires a
PostgreSQL + pgvector instance. The canonical flow runs everything
in-network with containers only:

```bash
# 1. Build the test image once (lock-exact deps, dev group included)
podman build -f infra/podman/Containerfile --target test -t dafi-sentinel-test:local .

# 2. Start an isolated pgvector on a scratch network
podman network create dafi-sentinel-test-net
podman run -d --name sentinel-pg-smoke --network dafi-sentinel-test-net \
  -e POSTGRES_USER=sentinel -e POSTGRES_PASSWORD=sentinel -e POSTGRES_DB=sentinel \
  docker.io/pgvector/pgvector:pg16

# 3. Wait for readiness, then run the smoke against the in-network DSN
#    (env-only switch — no code change)
podman run --rm --network dafi-sentinel-test-net \
  --entrypoint '["python","/opt/dafi/wait_for_postgres.py","pytest","tests/dafi_sentinel/test_pgvector_adapter.py","-v"]' \
  -e DAFI_PGVECTOR_SMOKE=1 \
  -e DAFI_PGVECTOR_DSN=postgresql://sentinel:sentinel@sentinel-pg-smoke:5432/sentinel \
  dafi-sentinel-test:local

# 4. Teardown
podman rm -f sentinel-pg-smoke && podman network rm dafi-sentinel-test-net
```

Prefer Compose orchestration? The same stack serves both:

```bash
podman-compose -f infra/podman/compose.yaml up -d                   # postgres only → 127.0.0.1:55432
podman-compose -f infra/podman/compose.yaml --profile api up -d     # + API → http://127.0.0.1:8000
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/docs # expect 200
podman-compose -f infra/podman/compose.yaml --profile api down      # add -v to drop volumes
```

Host-side legacy flow (uses the published port): set
`DAFI_PGVECTOR_DSN=postgresql://sentinel:sentinel@127.0.0.1:55432/sentinel`
with `DAFI_PGVECTOR_SMOKE=1`.

The smoke test indexes a runbook and a decoy document, queries the
``RetrievalIndex`` contract against a live vector database, and asserts
that the runbook is ranked first.

## ML analysis and chart rendering (PR4)

PR4 ships deterministic incident analysis and a controlled chart
renderer. The scikit-learn pipeline lives in
``dafi_sentinel/ml/analysis.py``; the renderer and its spec validator
live in ``dafi_sentinel/charts/``. Both are pure-Python services that
work without any external infrastructure:

* ``dafi_sentinel.ml.analysis.score_anomalies`` — seeded
  ``IsolationForest`` scores per evidence ID, stable across runs.
* ``dafi_sentinel.ml.analysis.cluster_logs`` — seeded ``KMeans``
  cluster labels per evidence ID.
* ``dafi_sentinel.ml.analysis.rank_similarity`` — TF-IDF + cosine
  ranking against a query, descending by score and tied on evidence
  ID.
* ``dafi_sentinel.charts.validation.validate_chart_spec`` — rejects
  empty titles, missing evidence citations, and missing axis fields.
* ``dafi_sentinel.charts.renderer.render_chart`` — headless
  ``Agg``-backend matplotlib that returns PNG ``bytes`` (or writes to
  an explicit path) and never calls ``plt.show``.

Run the slice tests:

```bash
podman run --rm dafi-sentinel-test:local pytest \
  tests/dafi_sentinel/test_ml_analysis.py \
  tests/dafi_sentinel/test_chart_validation.py \
  tests/dafi_sentinel/test_chart_renderer.py -v
```

## Workbench API and dashboard (PR5)

PR5 ships the FastAPI workbench surface and the React + TypeScript +
Vite dashboard. The Python side lives under ``dafi_sentinel/api/`` and
the dashboard lives in ``frontend/``.

### Run the API

```bash
# 1. Postgres only by default; add the API with the profile (loopback :8000)
podman-compose -f infra/podman/compose.yaml --profile api up -d

# 2. Verify it is up
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/docs   # expect 200

# 3. Inspect the app factory without starting a server:
podman run --rm dafi-sentinel-api:local \
  python -c "from dafi_sentinel.api.app import create_workbench_app; print(create_workbench_app.__doc__)"
```

> R4 crit#1: ``default_workbench_app`` is a **dev-only** factory. It
> disables ``cookie_secure``, uses an in-memory user store, and
> generates a random on-boot password for the seeded users. It
> refuses to start when the ``DAFI_PRODUCTION_POSTURE=1`` env var
> is set so a misconfiguration (e.g., a production deploy that
> accidentally re-uses the dev factory) fails fast at boot.
>
> **Production posture** — set ``DAFI_PRODUCTION_POSTURE=1`` and use
> :func:`dafi_sentinel.api.app.create_workbench_app` with a real
> user store and ``cookie_secure=True``:

The env vars below configure the dev factory. Container runs pass them to
the compose `api` service via its `environment:` block (see the
commented `DAFI_DEV_PASSWORD` example in `infra/podman/compose.yaml`);
the host-based commands are shown only to illustrate factory semantics:

```bash
# 1. Generate a stable dev-only password (skip in CI):
export DAFI_DEV_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(16))')"

# 2. Run the dev server (containerized — see compose flow above; the
#    wait_for_postgres handoff execs uvicorn after DB readiness):
#    the compose api entrypoint is: python /opt/dafi/wait_for_postgres.py uvicorn ...

# 3. In production, set DAFI_PRODUCTION_POSTURE=1 to refuse the dev factory:
export DAFI_PRODUCTION_POSTURE=1
uv run gunicorn myapp:create_production_app  # the dev factory raises RuntimeError
```

The API surface is:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST`   | `/sessions`             | none | login; sets an HttpOnly session cookie |
| `DELETE` | `/sessions/me`          | cookie | logout; clears the session cookie |
| `DELETE` | `/sessions/{token}`     | bearer + path match | logout (bearer fallback for non-browser clients) |
| `GET`    | `/sessions/me`          | cookie or bearer | current user + roles |
| `GET`    | `/evidence`             | cookie or bearer | owned evidence list |
| `GET`    | `/evidence/{id}`        | cookie or bearer | owned evidence detail (404 / 403) |
| `POST`   | `/qa`                   | cookie or bearer | RAG Q&A with cited evidence IDs |
| `POST`   | `/charts`               | cookie or bearer | render a chart, returns PNG base64 |
| `GET`    | `/roles/{user_id}`      | cookie or bearer + ownership | role + permission lookup |
| `GET`    | `/audits`               | cookie or bearer | actor-scoped audit list |

#### Session transport (CRIT-1 fix)

The session is delivered to the browser as an HttpOnly+Secure+SameSite=strict
cookie named ``dafi_sentinel_session``. The login response body
contains only the user profile (no token) so an XSS payload cannot
exfiltrate the long-lived token. The dashboard sends
``credentials: 'include'`` on every request so the browser attaches
the cookie automatically. Non-browser clients (curl, CLI) can still
authenticate via the ``Authorization: Bearer <token>`` header — the
login response sets the same token in the ``Set-Cookie`` header, so a
client can copy it from there and use it as a bearer. The bearer
header is a fallback kept for ergonomic dev workflows; the cookie is
the primary transport.

Every stateful action writes an ``AuditRecord`` through the
``AuditRepository`` contract. The seeded users are:

| user id | display name | username | password | roles |
|---|---|---|---|---|
| `user-1` | Analyst    | `ada`  | *(random on boot — see below)*     | analyst (tool:search, chart:request) |
| `user-2` | Maintainer | `mike` | *(random on boot — see below)* | maintainer (tool:python) |

> R1 high#1: the dev server no longer ships with a plaintext seeded
> password. On boot, ``default_workbench_app`` generates a fresh
> password for each seeded user and prints it to the server log. The
> ``DAFI_DEV_PASSWORD`` environment variable overrides the random
> generation with a stable dev-only credential so scripts and CI can
> pin the password without checking it into source control. The
> dev-only posture is documented in
> ``dafi_sentinel.api.app.default_workbench_app``.

### Run the dashboard

```bash
cd frontend
npm install
npm run dev      # http://127.0.0.1:5173, proxies /sessions, /evidence,
                 # /qa, /charts, /roles, /audits to http://127.0.0.1:8000
```

The dashboard uses TanStack Query for server state, Recharts for
chart panels, Vitest + Testing Library for component tests, and
redirects unauthenticated users to ``/login`` via the ``AuthGate``
wrapper. A 401 or 403 from the workbench server is rendered inline
on the page that triggered it.

### Run the slice tests

```bash
# Backend (containerized, lock-exact)
podman run --rm dafi-sentinel-test:local pytest \
  tests/dafi_sentinel/test_api_auth.py \
  tests/dafi_sentinel/test_api_endpoints.py -v

# Frontend (host-based until PR-B)
cd frontend && npm run test && npm run build
```

## Later slices

PR6 ships the LangGraph orchestration layer: a state machine that
composes the existing PR1-PR5 services and pauses for human approval
before controlled actions (chart rendering). Grafana, Prometheus, and
production telemetry are explicitly out of scope for this product.

### LangGraph orchestration (PR6)

The investigation workflow is a scoped state machine that lives under
``dafi_sentinel/orchestration/``:

* ``dafi_sentinel.orchestration.graph.build_investigation_graph`` — the
  compiled state graph factory. Takes a ``WorkbenchService`` (PR5), a
  ``SecurityGate`` (PR2), and an ``AuditRepository`` (PR1) and returns
  a LangGraph ``CompiledStateGraph`` wired with an ``InMemorySaver``
  checkpointer.
* ``InvestigationState`` — the ``TypedDict`` describing the graph
  state (actor, session, question, cited evidence, answer, chart PNG,
  approval decision, audit accumulator).
* ``ApprovalRequest`` — the payload exchanged at the approval node
  (``approved``, ``approver_id``).

The graph visits these nodes in order:

| Node | Service | Audit action |
|------|---------|--------------|
| `inspect` | `SecurityGate.inspect_user_request` (PR2) | `orchestration.inspect` |
| `retrieve` | `WorkbenchService.answer_question` (PR3 + PR4) | `orchestration.retrieve` |
| `compose_answer` | fold cited evidence into the answer | — |
| `request_approval` | `langgraph.types.interrupt` pause | `orchestration.approval` |
| `render_chart` | `WorkbenchService.render_chart` (PR4) | `orchestration.render_chart` |
| `finalize` | terminal audit writer | `orchestration.finalize` |

The approval node calls ``langgraph.types.interrupt(...)``; a separate
test helper (or future CLI) resumes the graph with an
``ApprovalRequest`` via ``Command(resume=...)``. When the approver
refuses, the graph skips the chart render and the finalize node
records ``PolicyDecision(allowed=False, reason="approval-denied")``.

Run the slice tests:

```bash
podman run --rm dafi-sentinel-test:local pytest tests/dafi_sentinel/test_orchestration.py -v
```
