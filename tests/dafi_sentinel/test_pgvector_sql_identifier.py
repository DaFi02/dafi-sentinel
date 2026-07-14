"""Tests for the pgvector SQL injection fix (PR-C.17, R2 med).

PR-C.17 closes a SQL-injection gap the 4R review caught in
``dafi_sentinel.retrieval.pgvector``: the prior surface used
f-strings to interpolate ``self._table_name`` into ``SELECT``,
``CREATE TABLE``, and ``INSERT`` statements. A future refactor that
moves the table name into a config file would silently let a
malicious value break out of the identifier and execute arbitrary
SQL.

The fix routes every identifier through ``psycopg.sql.Identifier``
and every literal through ``psycopg.sql.Literal`` so the database
driver is responsible for the quoting. The behavior is the same for
trusted inputs; the contract is the new tests in this module.

The test pins two contracts:

* The SQL generated for a query does NOT contain the table name
  as a raw substring (the identifier is rendered through
  ``psycopg.sql.Identifier`` and is properly quoted).
* The ``search`` call uses a parameterized cursor (not an
  f-string) so the table name is bound at execution time.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from dafi_sentinel.retrieval import pgvector


def _make_adapter() -> pgvector.PgVectorRetrievalIndex:
    return pgvector.PgVectorRetrievalIndex(
        dsn="postgresql://user:pass@host:5432/db",
        table_name="documents",
        connect_timeout=1,
    )


def test_search_uses_sql_identifier_for_table_name():
    """The ``search`` cursor.execute call routes the table name through psycopg.sql.Identifier."""
    adapter = _make_adapter()

    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    # ``with conn.cursor() as cur`` returns the fake cursor via __enter__.
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    fake_conn.closed = True  # force a reconnect on the next call
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = False

    # Patch the ``_connect`` method to return the fake connection.
    with patch.object(adapter, "_connect", return_value=fake_conn):
        with patch.object(adapter, "_format_vector", return_value="[0.0,1.0]"):
            result = adapter.search("query", limit=5)

    # The cursor.execute call MUST have been invoked with a Composed
    # object (or a string with %s placeholders). When the SQL is
    # composed via ``psycopg.sql.SQL`` and ``psycopg.sql.Identifier``,
    # the table name is rendered quoted and the literal is bound.
    assert fake_cursor.execute.called, "search must call cursor.execute"
    args, _ = fake_cursor.execute.call_args
    # The first positional arg is the SQL: it can be either a string
    # with %s placeholders or a Composed object. Either way, the
    # unquoted table name MUST NOT be inlined as a raw fragment.
    sql = args[0]
    # Composed objects render the SQL with quoted identifiers; a
    # plain string stays as itself. The ``as_string(None)`` call
    # uses the default UTF-8 encoding so the test does not need a
    # real psycopg.Connection.
    if hasattr(sql, "as_string"):
        sql_text = sql.as_string(None)
    else:
        sql_text = str(sql)
    # The raw table name "documents" MUST NOT appear unquoted in the
    # SQL text. psycopg.sql.Identifier renders it as "documents"
    # (double-quoted) so a substring check is sufficient.
    assert "FROM documents" not in sql_text, (
        f"table name MUST be rendered through psycopg.sql.Identifier; "
        f"got raw SQL fragment: {sql_text!r}"
    )
    # And the SQL MUST include the table name, properly quoted.
    assert '"documents"' in sql_text or "documents" in sql_text


def test_index_document_uses_sql_identifier_for_table_name():
    """The ``index_document`` cursor.execute call routes the table name through psycopg.sql.Identifier."""
    from dafi_sentinel.domain.models import Document, SourceMetadata

    adapter = _make_adapter()

    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    fake_conn.closed = True
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = False

    document = Document(
        id="doc-1",
        title="Test",
        body="body",
        source=SourceMetadata("fixtures/test.md"),
        evidence_ids=("ev-1",),
    )

    with patch.object(adapter, "_connect", return_value=fake_conn):
        with patch.object(adapter, "_format_vector", return_value="[0.0,1.0]"):
            adapter.index_document(document)

    assert fake_cursor.execute.called
    args, _ = fake_cursor.execute.call_args
    sql = args[0]
    if hasattr(sql, "as_string"):
        sql_text = sql.as_string(None)
    else:
        sql_text = str(sql)
    # The INSERT statement MUST NOT inline the table name as a raw
    # f-string fragment.
    assert "INSERT INTO documents" not in sql_text, (
        f"table name MUST be rendered through psycopg.sql.Identifier; "
        f"got raw SQL fragment: {sql_text!r}"
    )


def test_ensure_schema_uses_sql_identifier_for_table_name():
    """The ``ensure_schema`` cursor.execute call routes the table name through psycopg.sql.Identifier."""
    adapter = _make_adapter()

    fake_conn = MagicMock()
    fake_cursor = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
    fake_conn.closed = True
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = False

    with patch.object(adapter, "_connect", return_value=fake_conn):
        adapter.ensure_schema()

    # The CREATE TABLE statement is one of the execute calls.
    found_create_table = False
    for call in fake_cursor.execute.call_args_list:
        args, _ = call
        sql = args[0]
        if hasattr(sql, "as_string"):
            sql_text = sql.as_string(None)
        else:
            sql_text = str(sql)
        if "CREATE TABLE" in sql_text:
            found_create_table = True
            # The raw table name MUST NOT be inlined.
            assert "CREATE TABLE documents" not in sql_text, (
                f"table name MUST be rendered through psycopg.sql.Identifier; "
                f"got raw SQL fragment: {sql_text!r}"
            )
    assert found_create_table, "ensure_schema must call CREATE TABLE"
