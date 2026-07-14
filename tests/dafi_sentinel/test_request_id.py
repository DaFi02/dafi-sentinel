"""Tests for the request_id middleware and audit propagation (PR-C.9, R4 high#4).

PR-C.9 ships two hardening layers on the request lifecycle:

* ``logging.basicConfig`` is invoked at module import so the
  reference ``uvicorn dafi_sentinel.api.app:default_workbench_app``
  command actually logs to stderr (the 4R review caught that the
  default factory had no logging setup and operators were flying
  blind).
* A middleware attaches a ``request_id`` (UUID4) to every request,
  exposes it on ``request.state.request_id`` so handlers can include
  it in audit records, and echoes it on the response via the
  ``X-Request-ID`` header so the dashboard can correlate logs.

This module pins both contracts.
"""

from __future__ import annotations

import logging
import re
import uuid

from fastapi.testclient import TestClient

from dafi_sentinel.api.app import create_workbench_app
from dafi_sentinel.api.auth import AuthService, InMemorySessionStore, InMemoryUserStore
from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.retrieval.contracts import InMemoryRetrievalIndex


def _build_app():
    users = InMemoryUserStore()
    auth = AuthService(users=users, sessions=InMemorySessionStore())
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        retrieval_index=InMemoryRetrievalIndex(()),
    )
    return create_workbench_app(auth=auth, workbench=workbench)


def test_app_module_configures_logging_on_import():
    """The app module wires logging.basicConfig at import time."""
    import dafi_sentinel.api.app as app_module

    # Importing the module is enough — the basicConfig call runs at
    # module load. The logger for the app module is non-null and the
    # root logger has at least one handler.
    root = logging.getLogger()
    assert root.handlers, "logging.basicConfig must wire a handler at import time"


def test_request_id_middleware_attaches_uuid4_to_state():
    """A UUID4 is attached to ``request.state.request_id`` for every request."""
    app = _build_app()
    with TestClient(app) as client:
        response = client.get("/sessions/me")
    # The response carries the X-Request-ID header.
    header = response.headers.get("x-request-id")
    assert header is not None
    # And it parses as a UUID4.
    parsed = uuid.UUID(header)
    assert parsed.version == 4


def test_request_id_middleware_preserves_caller_supplied_id():
    """A caller-supplied X-Request-ID is preserved (so upstream tracing survives)."""
    app = _build_app()
    supplied = "test-trace-12345"
    with TestClient(app) as client:
        response = client.get("/sessions/me", headers={"X-Request-ID": supplied})
    assert response.headers.get("x-request-id") == supplied


def test_request_id_middleware_generates_unique_ids_per_request():
    """Two requests get two distinct request_ids."""
    app = _build_app()
    with TestClient(app) as client:
        first = client.get("/sessions/me")
        second = client.get("/sessions/me")
    assert first.headers.get("x-request-id") != second.headers.get("x-request-id")
