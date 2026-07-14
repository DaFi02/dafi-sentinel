"""Production-ready graph factory (R4 crit#2, R4 high#2).

The default :func:`dafi_sentinel.orchestration.graph.build_investigation_graph`
compiles the investigation state machine with a process-local
:class:`langgraph.checkpoint.memory.InMemorySaver`. That is the right
choice for tests and the local dev server: it has zero external
dependencies and survives a single process lifetime.

Production deployments MUST swap the in-memory saver for a durable
checkpointer. The 4R review (R4 crit#2) caught that no shipped helper
shows operators how to do that. This module ships the helper:

* :func:`production_graph` — when the ``DAFI_PRODUCTION_GRAPH=1`` env
  var is set, the factory returns a graph compiled with a
  ``PostgresSaver`` built from ``DAFI_PGVECTOR_DSN``. When the env var
  is unset, the factory falls back to the in-memory default so the
  helper is safe to import from any context (including the test suite).
* :func:`_build_postgres_saver` — private helper that lazily imports
  ``langgraph.checkpoint.postgres.PostgresSaver`` so the test suite
  does not pay the import cost (or pull in ``psycopg-pool``) when the
  env var is unset.

The Postgres graph is intentionally opt-in: the 4R review (R4 high#2)
flagged that the prior reference README told operators to use
``PostgresSaver`` without any shipped code, which left room for
operator misconfiguration. The env-var gate also means the ``uv run
pytest`` run stays free of external dependencies — the default test
suite only sees the in-memory path.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dafi_sentinel.api.services import WorkbenchService
from dafi_sentinel.orchestration.graph import build_investigation_graph
from dafi_sentinel.security.policy import SecurityGate
from dafi_sentinel.storage.contracts import AuditRepository


logger = logging.getLogger(__name__)


_PRODUCTION_GRAPH_ENV = "DAFI_PRODUCTION_GRAPH"
_PGVECTOR_DSN_ENV = "DAFI_PGVECTOR_DSN"


def _build_postgres_saver(dsn: str):
    """Lazily construct a ``PostgresSaver`` for the supplied DSN.

    The import is deferred so the test suite (and the default
    ``uv run pytest`` run) does not pull in ``psycopg-pool`` when the
    in-memory path is used. Operators that opt into the production
    graph pay the cost once at boot.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    return PostgresSaver.from_conn_string(dsn)


def production_graph(
    *,
    workbench: WorkbenchService,
    gate: SecurityGate,
    audits: AuditRepository,
    dsn: str | None = None,
) -> Any:
    """Return the investigation graph configured for the deployment posture.

    Parameters
    ----------
    workbench:
        The :class:`WorkbenchService` instance the graph composes.
    gate:
        The :class:`SecurityGate` that owns the prompt-boundary policy.
    audits:
        The :class:`AuditRepository` every stateful node writes to.
    dsn:
        Optional PostgreSQL DSN. When ``None`` (the default), the
        function reads ``DAFI_PGVECTOR_DSN`` from the environment.

    Returns
    -------
    Any
        The compiled LangGraph state machine. With
        ``DAFI_PRODUCTION_GRAPH=1``, the graph is compiled with a
        :class:`PostgresSaver` so paused investigations survive process
        restarts. Without the env var, the default in-memory saver is
        used.

    Notes
    -----
    R4 high#2: the production path is gated on an env var (not a
    boolean argument) so a misconfigured deploy that forgets to set
    ``DAFI_PRODUCTION_GRAPH=1`` keeps the in-memory saver and the
    failed-deploy symptom is "paused investigations vanished after
    restart" — the same symptom operators would see if they forgot to
    deploy the checkpointer at all. The env-var gate also keeps the
    ``uv run pytest`` run free of external dependencies.
    """
    if os.environ.get(_PRODUCTION_GRAPH_ENV) != "1":
        logger.debug(
            "DAFI_PRODUCTION_GRAPH is not set; production_graph() is "
            "returning the in-memory default. Set DAFI_PRODUCTION_GRAPH=1 "
            "and DAFI_PGVECTOR_DSN to use PostgresSaver."
        )
        return build_investigation_graph(
            workbench=workbench,
            gate=gate,
            audits=audits,
        )

    resolved_dsn = dsn or os.environ.get(_PGVECTOR_DSN_ENV)
    if not resolved_dsn:
        raise RuntimeError(
            "DAFI_PRODUCTION_GRAPH=1 requires DAFI_PGVECTOR_DSN to be set "
            "with the PostgreSQL connection string."
        )

    logger.info(
        "DAFI_PRODUCTION_GRAPH=1; compiling the investigation graph with "
        "PostgresSaver backed by DAFI_PGVECTOR_DSN."
    )
    checkpointer = _build_postgres_saver(resolved_dsn)
    return build_investigation_graph(
        workbench=workbench,
        gate=gate,
        audits=audits,
        checkpointer=checkpointer,
    )


__all__ = ["production_graph"]
