# DAFI Sentinel

DAFI Sentinel is a security-first incident investigation workbench.

## Quick start

```bash
uv sync
uv run pytest
```

The default pytest run needs no live database, Podman, or external service.

## Run the pgvector smoke (PR3)

The pgvector retrieval adapter has an opt-in smoke test that requires a
local PostgreSQL + pgvector instance. Start it with Podman Compose and run
the smoke:

```bash
podman compose -f infra/podman/compose.yaml up -d
DAFI_PGVECTOR_SMOKE=1 \
DAFI_PGVECTOR_DSN=postgresql://sentinel:sentinel@127.0.0.1:55432/sentinel \
  uv run pytest tests/dafi_sentinel/test_pgvector_adapter.py -v
podman compose -f infra/podman/compose.yaml down -v
```

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
uv run pytest tests/dafi_sentinel/test_ml_analysis.py \
               tests/dafi_sentinel/test_chart_validation.py \
               tests/dafi_sentinel/test_chart_renderer.py -v
```

## Workbench API and dashboard (PR5)

PR5 ships the FastAPI workbench surface and the React + TypeScript +
Vite dashboard. The Python side lives under ``dafi_sentinel/api/`` and
the dashboard lives in ``frontend/``.

### Run the API

```bash
# 1. Start the FastAPI server (default in-memory services, seeded
#    with one analyst and one maintainer).
uv run uvicorn dafi_sentinel.api.app:default_workbench_app --reload

# 2. Or build a custom app from your own services:
uv run python -c "from dafi_sentinel.api.app import create_workbench_app; print(create_workbench_app.__doc__)"
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

```bash
# 1. Generate a stable dev-only password (skip in CI):
export DAFI_DEV_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(16))')"

# 2. Run the dev server:
uv run uvicorn dafi_sentinel.api.app:default_workbench_app --reload

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
# Backend
uv run pytest tests/dafi_sentinel/test_api_auth.py \
               tests/dafi_sentinel/test_api_endpoints.py -v

# Frontend
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
uv run pytest tests/dafi_sentinel/test_orchestration.py -v
```
