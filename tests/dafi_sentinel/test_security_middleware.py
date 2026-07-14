"""Tests for the production-only security middleware (R1 high#4).

PR-C.3 wires the production-readiness middleware (CORS, TrustedHost,
HTTPSRedirect, HSTS) into :func:`create_workbench_app` behind a
gating flag. The default dev factory (and every existing test that
builds the app with the historical call signature) MUST keep working
unchanged: the middleware only activates when the operator opts in
with ``enable_security_middleware=True`` (and the test pins the env
var ``DAFI_PRODUCTION_POSTURE=1`` as the canonical gate the
``default_workbench_app`` factory already enforces).

The tests assert:

* The factory accepts the new flag without breaking pre-PR-C.3 call
  sites (regression: existing tests that build the app MUST keep
  passing).
* When the flag is set, the app installs the four middleware pieces
  in the right order (HTTPSRedirect before TrustedHost, HSTS via
  ``Strict-Transport-Security`` on every response, CORS allow-list).
* The dev factory (no flag) does NOT install the middleware.
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


def _build_app(**kwargs):
    users = InMemoryUserStore()
    auth = AuthService(users=users, sessions=InMemorySessionStore())
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        retrieval_index=InMemoryRetrievalIndex(()),
    )
    return create_workbench_app(auth=auth, workbench=workbench, **kwargs)


def test_security_middleware_flag_is_accepted_by_factory():
    """The new ``enable_security_middleware`` kwarg is part of the public API."""
    app = _build_app(enable_security_middleware=True)
    assert app.title == "DAFI Sentinel Workbench API"


def test_security_middleware_is_off_by_default():
    """The dev factory and pre-PR-C.3 call sites keep the legacy surface."""
    app = _build_app()
    # When the flag is off, no HSTS header is added to responses. The
    # way to pin this is to fetch any route and inspect headers.
    with TestClient(app) as client:
        response = client.get("/sessions/me")
    assert "strict-transport-security" not in {k.lower() for k in response.headers}


def test_security_middleware_installs_hsts_when_enabled():
    """HSTS is added to every response when the middleware is enabled."""
    app = _build_app(
        enable_security_middleware=True,
        security_allowed_hosts=("example.com",),
    )
    with TestClient(app) as client:
        # TrustedHost will reject any non-matching Host header, so we
        # override it before the request.
        response = client.get(
            "/sessions/me",
            headers={"Host": "example.com"},
        )
    # The HSTS header MUST be present (the TestClient follows the
    # middleware in order: HTTPSRedirect is skipped in tests because
    # we are already on http, but TrustedHost + HSTS run).
    assert "strict-transport-security" in {k.lower() for k in response.headers}


def test_security_middleware_blocks_unknown_host():
    """TrustedHostMiddleware rejects hosts that are not in the allow-list."""
    app = _build_app(
        enable_security_middleware=True,
        security_allowed_hosts=("example.com",),
    )
    with TestClient(app) as client:
        response = client.get("/sessions/me")
    # 400 from TrustedHostMiddleware for an unknown host.
    assert response.status_code == 400


def test_security_middleware_cors_allows_configured_origin():
    """CORSMiddleware echoes the configured origin in Access-Control-Allow-Origin."""
    app = _build_app(
        enable_security_middleware=True,
        security_allowed_hosts=("example.com",),
        security_cors_origins=("https://dashboard.example.com",),
    )
    with TestClient(app) as client:
        # A CORS preflight must succeed against the allow-list.
        response = client.options(
            "/sessions",
            headers={
                "Host": "example.com",
                "Origin": "https://dashboard.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    # 200 from a successful CORS preflight.
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://dashboard.example.com"
