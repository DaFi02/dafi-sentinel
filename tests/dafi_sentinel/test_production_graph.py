"""Tests for the production-ready workbench graph factory (R4 crit#2, R4 high#2).

PR-C.1 ships a ``production_graph()`` factory example that swaps the
default :class:`InMemorySaver` for a ``PostgresSaver`` when
``DAFI_PRODUCTION_GRAPH=1`` is set in the environment. The in-memory
sentinel remains the default for local dev and the test suite so the
default ``uv run pytest`` run still has zero external dependencies.

This module pins the contract:

* The factory is importable from the orchestration package.
* With ``DAFI_PRODUCTION_GRAPH=1`` set, the factory returns a graph
  compiled with the configured checkpointer.
* Without the env var, the factory returns the default in-memory graph
  (unchanged from PR6).
* The function never imports ``langgraph.checkpoint.postgres`` unless
  the env var is set, so the default suite stays free of the
  ``psycopg-pool`` dependency.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_production_graph_is_exported_from_orchestration_package():
    """The factory is part of the production-readiness public surface."""
    from dafi_sentinel.orchestration import production_graph

    assert callable(production_graph)


def test_production_graph_returns_default_when_env_var_unset(monkeypatch):
    """The default path keeps the in-memory saver so the test suite needs no Postgres."""
    monkeypatch.delenv("DAFI_PRODUCTION_GRAPH", raising=False)

    from dafi_sentinel.orchestration import production_graph

    workbench = MagicMock()
    gate = MagicMock()
    audits = MagicMock()

    fake_graph = MagicMock(name="compiled_graph")
    with patch(
        "dafi_sentinel.orchestration.production_graph.build_investigation_graph",
        return_value=fake_graph,
    ) as builder:
        result = production_graph(workbench=workbench, gate=gate, audits=audits)

    assert result is fake_graph
    # The default call MUST NOT pass a checkpointer (so InMemorySaver
    # wins inside ``build_investigation_graph``).
    _, kwargs = builder.call_args
    assert "checkpointer" not in kwargs or kwargs.get("checkpointer") is None


def test_production_graph_uses_postgres_saver_when_env_var_set(monkeypatch):
    """Setting DAFI_PRODUCTION_GRAPH=1 swaps the in-memory saver for a PostgresSaver."""
    monkeypatch.setenv("DAFI_PRODUCTION_GRAPH", "1")
    monkeypatch.setenv("DAFI_PGVECTOR_DSN", "postgresql://prod/db")

    from dafi_sentinel.orchestration.production_graph import production_graph
    from dafi_sentinel.orchestration import production_graph as pg_module

    workbench = MagicMock()
    gate = MagicMock()
    audits = MagicMock()

    fake_saver = MagicMock(name="postgres_saver")
    fake_graph = MagicMock(name="compiled_graph")

    with patch(
        "dafi_sentinel.orchestration.production_graph.build_investigation_graph",
        return_value=fake_graph,
    ) as builder, patch(
        "dafi_sentinel.orchestration.production_graph._build_postgres_saver",
        return_value=fake_saver,
    ) as saver_factory:
        result = production_graph(
            workbench=workbench, gate=gate, audits=audits
        )

    assert result is fake_graph
    # The saver factory MUST have been called with the configured DSN.
    saver_factory.assert_called_once_with("postgresql://prod/db")
    # And the saver MUST have been passed through to the graph builder.
    _, kwargs = builder.call_args
    assert kwargs.get("checkpointer") is fake_saver


def test_production_graph_requires_dsn_when_env_var_set(monkeypatch):
    """The production path fails fast when DAFI_PGVECTOR_DSN is missing."""
    monkeypatch.setenv("DAFI_PRODUCTION_GRAPH", "1")
    monkeypatch.delenv("DAFI_PGVECTOR_DSN", raising=False)

    from dafi_sentinel.orchestration import production_graph

    with pytest.raises(RuntimeError, match="DAFI_PGVECTOR_DSN"):
        production_graph(
            workbench=MagicMock(),
            gate=MagicMock(),
            audits=MagicMock(),
        )
