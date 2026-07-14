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

## Later slices

FastAPI, React + TypeScript + Vite, auth middleware, LangGraph, and
scikit-learn arrive in PR4, PR5, and PR6. Grafana and Prometheus are
explicitly out of scope for this product.
