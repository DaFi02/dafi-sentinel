"""Tests for the PostgreSQL + pgvector retrieval adapter.

The pgvector adapter is the staging port that connects the deterministic
``RetrievalIndex`` contract to a live vector database. The unit-level cases
validate the adapter's pure helpers (embedding, error surface, protocol
conformance) and the smoke case proves a real Podman pgvector instance
satisfies the same contract.
"""

from __future__ import annotations

import os

import pytest

from dafi_sentinel.domain.models import Document, SourceMetadata
from dafi_sentinel.retrieval.contracts import RetrievalIndex


SMOKE_ENV = "DAFI_PGVECTOR_SMOKE"
DSN_ENV = "DAFI_PGVECTOR_DSN"


# ---------------------------------------------------------------------------
# Unit tests — always run, never require a live PostgreSQL instance.
# ---------------------------------------------------------------------------


def test_pgvector_adapter_module_is_importable():
    """Adapter module is part of the PR3 retrieval slice and must import cleanly."""
    from dafi_sentinel.retrieval import pgvector  # noqa: F401


def test_pgvector_adapter_satisfies_retrieval_index_protocol():
    """``PgVectorRetrievalIndex`` must be a structural subtype of ``RetrievalIndex``.

    The protocol is what the rest of the product depends on; if the adapter
    does not satisfy it, swapping adapters (fixture <-> pgvector) breaks.
    """
    from dafi_sentinel.retrieval import pgvector

    adapter = pgvector.PgVectorRetrievalIndex(
        dsn="postgresql://invalid-host:5432/none",
        table_name="smoke_documents",
        connect_timeout=1,
    )

    assert isinstance(adapter, RetrievalIndex)
    assert hasattr(adapter, "search")
    assert callable(adapter.search)


def test_pgvector_embedding_is_deterministic_for_identical_text():
    """Embedding must be stable so the smoke test is reproducible."""
    from dafi_sentinel.retrieval import pgvector

    adapter = pgvector.PgVectorRetrievalIndex(
        dsn="postgresql://invalid-host:5432/none",
        table_name="smoke_documents",
        embedding_dim=16,
    )

    vec_a = adapter._embed_text("checkout latency regression")
    vec_b = adapter._embed_text("checkout latency regression")
    vec_c = adapter._embed_text("totally unrelated question")

    assert vec_a == vec_b
    assert vec_a != vec_c
    assert len(vec_a) == 16
    assert all(isinstance(value, float) for value in vec_a)


def test_pgvector_embedding_handles_empty_text_without_crashing():
    """Empty text must produce a zero vector instead of raising."""
    from dafi_sentinel.retrieval import pgvector

    adapter = pgvector.PgVectorRetrievalIndex(
        dsn="postgresql://invalid-host:5432/none",
        table_name="smoke_documents",
        embedding_dim=8,
    )

    vec = adapter._embed_text("")

    assert len(vec) == 8
    assert all(value == 0.0 for value in vec)


def test_pgvector_format_vector_emits_pgvector_literal():
    """Vector literal must be the pgvector text format ``[v1,v2,...]`` with float precision."""
    from dafi_sentinel.retrieval import pgvector

    literal = pgvector.PgVectorRetrievalIndex._format_vector([0.1, 0.2, 0.3])

    assert literal.startswith("[")
    assert literal.endswith("]")
    inner = literal[1:-1].split(",")
    assert len(inner) == 3
    assert all(value == f"{float(value):.6f}" for value in inner)


def test_pgvector_adapter_surfaces_clear_error_when_unreachable():
    """A short-timeout connection to an invalid host must raise ``PgVectorConnectionError``."""
    from dafi_sentinel.retrieval import pgvector

    adapter = pgvector.PgVectorRetrievalIndex(
        dsn="postgresql://127.0.0.1:1/none",
        table_name="smoke_documents",
        connect_timeout=1,
    )

    with pytest.raises(pgvector.PgVectorConnectionError):
        adapter._connect()


def test_pgvector_search_short_circuits_without_db_for_zero_limit():
    """Search must return ``[]`` for ``limit <= 0`` without touching PostgreSQL."""
    from dafi_sentinel.retrieval import pgvector

    adapter = pgvector.PgVectorRetrievalIndex(
        dsn="postgresql://127.0.0.1:1/none",
        table_name="smoke_documents",
        connect_timeout=1,
    )

    assert adapter.search("anything", limit=0) == []
    assert adapter.search("anything", limit=-1) == []
    assert adapter.search("", limit=5) == []
    assert adapter.search("   ", limit=5) == []


def test_pgvector_embedding_is_l2_normalised():
    """Non-empty embeddings must have unit L2 norm for stable cosine distance."""
    import math

    from dafi_sentinel.retrieval import pgvector

    adapter = pgvector.PgVectorRetrievalIndex(
        dsn="postgresql://invalid:5432/none",
        table_name="smoke_documents",
        embedding_dim=12,
    )

    vec = adapter._embed_text("checkout payment latency regression")

    norm = math.sqrt(sum(value * value for value in vec))
    assert math.isclose(norm, 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Smoke test — runs only when DAFI_PGVECTOR_SMOKE=1 and DAFI_PGVECTOR_DSN is set.
# ---------------------------------------------------------------------------


SMOKE_TABLE_PREFIX = "smoke_documents"


@pytest.mark.skipif(
    os.environ.get(SMOKE_ENV) != "1",
    reason=(
        f"set {SMOKE_ENV}=1 and {DSN_ENV}=<pgvector dsn> to exercise the live pgvector smoke; "
        "see README.md podman quickstart."
    ),
)
def test_pgvector_smoke_indexes_runbook_and_returns_evidence_references():
    """End-to-end: index a runbook, query, get ranked evidence refs from the same port."""
    import psycopg

    from dafi_sentinel.retrieval import pgvector

    dsn = os.environ[DSN_ENV]
    table = f"{SMOKE_TABLE_PREFIX}_{os.getpid()}"

    try:
        adapter = pgvector.PgVectorRetrievalIndex(
            dsn=dsn,
            table_name=table,
            embedding_dim=16,
            connect_timeout=5,
        )
        adapter.ensure_schema()

        runbook = Document(
            id="runbook-checkout-latency",
            title="Checkout Latency Runbook",
            body=(
                "When checkout latency regresses, compare deployment timing "
                "and payment dependency health before paging on-call."
            ),
            source=SourceMetadata(
                uri="tests/dafi_sentinel/fixtures/checkout_latency_runbook.md",
            ),
            evidence_ids=("ev-inc-001-fixtures-incidents-checkout-jsonl-row-1",),
        )
        unrelated = Document(
            id="runbook-network",
            title="Network Connectivity Guide",
            body="How to diagnose a VPN tunnel drop in corporate offices.",
            source=SourceMetadata(
                uri="tests/dafi_sentinel/fixtures/network_runbook.md",
            ),
            evidence_ids=("ev-network-001",),
        )
        adapter.index_document(runbook)
        adapter.index_document(unrelated)

        results = adapter.search("checkout latency payment", limit=3)

        assert len(results) >= 1
        assert results[0].evidence_id == "ev-inc-001-fixtures-incidents-checkout-jsonl-row-1"
        assert results[0].source.uri.endswith("checkout_latency_runbook.md")
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
