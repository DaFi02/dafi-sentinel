"""PostgreSQL + pgvector adapter for the ``RetrievalIndex`` port.

This adapter is the staged PR3 implementation that connects the deterministic
``RetrievalIndex`` contract (see :mod:`dafi_sentinel.retrieval.contracts`) to
a real vector database. PR1 only knows about fixture/in-memory adapters; PR3
adds the pgvector port so runbook/document retrieval can move from unit
fixtures to a Podman-managed PostgreSQL without touching the call sites.

The adapter is intentionally minimal and deterministic:

* Text is embedded with a stable bag-of-tokens hash so the smoke test is
  reproducible and no heavyweight ML dependency is pulled into PR3.
* Connections are lazy and time-bounded; failure surfaces a single
  ``PgVectorConnectionError`` so callers can fall back to the in-memory
  adapter.
* The schema (``CREATE EXTENSION vector``, ``CREATE TABLE``) is created on
  demand by :meth:`PgVectorRetrievalIndex.ensure_schema`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from dafi_sentinel.domain.models import Document, EvidenceRef


class PgVectorConnectionError(RuntimeError):
    """Raised when the adapter cannot reach the configured PostgreSQL instance."""


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class _EmbeddedDocument:
    """Internal record produced by :meth:`PgVectorRetrievalIndex._embed_document`."""

    doc_id: str
    title: str
    body: str
    source_uri: str
    source_row: int | None
    source_offset: int | None
    embedding: list[float]
    evidence_ids: tuple[str, ...]


class PgVectorRetrievalIndex:
    """PostgreSQL + pgvector implementation of the ``RetrievalIndex`` port."""

    def __init__(
        self,
        dsn: str,
        table_name: str = "documents",
        embedding_dim: int = 32,
        connect_timeout: int = 5,
    ) -> None:
        if embedding_dim <= 0:
            raise ValueError("embedding_dim must be positive")
        self._dsn = dsn
        self._table_name = table_name
        self._embedding_dim = embedding_dim
        self._connect_timeout = connect_timeout
        self._conn: psycopg.Connection | None = None

    # ------------------------------------------------------------------ #
    # Contract: RetrievalIndex.search
    # ------------------------------------------------------------------ #

    def search(self, query: str, limit: int) -> list[EvidenceRef]:
        if limit <= 0 or not query.strip():
            return []

        query_vec = self._embed_text(query)
        vector_literal = self._format_vector(query_vec)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT evidence_ids, source_uri, source_row, source_offset
                    FROM {self._table_name}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vector_literal, limit),
                )
                rows = cur.fetchall()

        results: list[EvidenceRef] = []
        for evidence_ids, source_uri, source_row, source_offset in rows:
            for evidence_id in evidence_ids:
                results.append(
                    EvidenceRef(
                        evidence_id=evidence_id,
                        source=_source_metadata(source_uri, source_row, source_offset),
                    )
                )
        return results

    # ------------------------------------------------------------------ #
    # Index management
    # ------------------------------------------------------------------ #

    def ensure_schema(self) -> None:
        """Create the pgvector extension and the configured table if missing."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._table_name} (
                        doc_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        body TEXT NOT NULL,
                        source_uri TEXT NOT NULL,
                        source_row INTEGER,
                        source_offset INTEGER,
                        embedding VECTOR({self._embedding_dim}) NOT NULL,
                        evidence_ids TEXT[] NOT NULL
                    )
                    """
                )
            conn.commit()

    def index_document(self, document: Document) -> None:
        """Embed and upsert a single document into the configured table."""
        embedded = self._embed_document(document)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self._table_name} (
                        doc_id, title, body, source_uri, source_row, source_offset, embedding, evidence_ids
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (doc_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        body = EXCLUDED.body,
                        source_uri = EXCLUDED.source_uri,
                        source_row = EXCLUDED.source_row,
                        source_offset = EXCLUDED.source_offset,
                        embedding = EXCLUDED.embedding,
                        evidence_ids = EXCLUDED.evidence_ids
                    """,
                    (
                        embedded.doc_id,
                        embedded.title,
                        embedded.body,
                        embedded.source_uri,
                        embedded.source_row,
                        embedded.source_offset,
                        self._format_vector(embedded.embedding),
                        list(embedded.evidence_ids),
                    ),
                )
            conn.commit()

    # ------------------------------------------------------------------ #
    # Embedding helpers (pure)
    # ------------------------------------------------------------------ #

    def _embed_document(self, document: Document) -> _EmbeddedDocument:
        text = f"{document.title} {document.body}"
        return _EmbeddedDocument(
            doc_id=document.id,
            title=document.title,
            body=document.body,
            source_uri=document.source.uri,
            source_row=document.source.row,
            source_offset=document.source.offset,
            embedding=self._embed_text(text),
            evidence_ids=tuple(document.evidence_ids),
        )

    def _embed_text(self, text: str) -> list[float]:
        """Deterministic bag-of-tokens hash embedding.

        Each token is hashed to a dimension index; repeated tokens increase
        the magnitude. The vector is L2-normalised so cosine distance via
        ``<=>`` stays numerically stable across documents of different
        lengths.
        """
        vector = [0.0] * self._embedding_dim
        for token in _TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._embedding_dim
            sign = 1.0 if (digest[4] & 1) else -1.0
            vector[index] += sign

        norm = sum(component * component for component in vector) ** 0.5
        if norm == 0.0:
            return vector
        return [component / norm for component in vector]

    @staticmethod
    def _format_vector(values: list[float]) -> str:
        """Render a Python list as the pgvector text literal ``[v1,v2,...]``."""
        return "[" + ",".join(f"{value:.6f}" for value in values) + "]"

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    def _connect(self) -> psycopg.Connection:
        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(
                    self._dsn,
                    connect_timeout=self._connect_timeout,
                )
                self._conn.autocommit = True
                with self._conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            if not getattr(self, "_vector_registered", False):
                register_vector(self._conn)
                self._vector_registered = True
            return self._conn
        except psycopg.OperationalError as exc:
            raise PgVectorConnectionError(str(exc)) from exc


def _source_metadata(uri: str, row: int | None, offset: int | None):
    from dafi_sentinel.domain.models import SourceMetadata

    return SourceMetadata(uri=uri, row=row, offset=offset)
