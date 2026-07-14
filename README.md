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

## Later slices

FastAPI, React + TypeScript + Vite, auth middleware, and LangGraph
arrive in PR5 and PR6. Grafana and Prometheus are explicitly out of
scope for this product.
