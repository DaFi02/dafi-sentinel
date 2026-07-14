"""Tests for the Cache-Control: no-store response header (PR-C.7, R1 high#4).

PR-C.7 ships a response-header policy on the sensitive endpoints so
browsers and intermediaries do not cache the responses. The 4R
review caught that the prior surface relied on the default
``Cache-Control`` (which lets browsers cache the response on disk).

The policy:

* ``/sessions`` and ``/audits`` get ``Cache-Control: no-store`` so
  an XSS payload that survives a logout cannot read the response
  body from the disk cache.
* Pre-PR-C.7 call sites keep the legacy surface (no header is
  added). The fix is opt-in via the ``enable_security_middleware``
  flag wired in PR-C.3 because the cache-control belongs to the
  same security posture.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from dafi_sentinel.api.app import create_workbench_app
from dafi_sentinel.api.auth import AuthService, InMemorySessionStore, InMemoryUserStore
from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.retrieval.contracts import InMemoryRetrievalIndex


def _build_app(*, enable_security_middleware: bool = False):
    users = InMemoryUserStore()
    auth = AuthService(users=users, sessions=InMemorySessionStore())
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        retrieval_index=InMemoryRetrievalIndex(()),
    )
    return create_workbench_app(
        auth=auth,
        workbench=workbench,
        enable_security_middleware=enable_security_middleware,
    )


def test_sessions_me_has_no_store_header_when_middleware_enabled():
    """/sessions/me sets Cache-Control: no-store when the security middleware is on."""
    app = _build_app(enable_security_middleware=True)
    with TestClient(app) as client:
        response = client.get(
            "/sessions/me",
            headers={"Host": "localhost"},
        )
    assert response.headers.get("cache-control") == "no-store"


def test_audits_has_no_store_header_when_middleware_enabled():
    """/audits sets Cache-Control: no-store when the security middleware is on."""
    app = _build_app(enable_security_middleware=True)
    with TestClient(app) as client:
        response = client.get(
            "/audits",
            headers={"Host": "localhost"},
        )
    assert response.headers.get("cache-control") == "no-store"


def test_legacy_call_sites_omit_cache_control():
    """The default (no security middleware) keeps the legacy surface."""
    app = _build_app()
    with TestClient(app) as client:
        response = client.get("/sessions/me")
    # No cache-control set by the application.
    assert "cache-control" not in {k.lower() for k in response.headers}
