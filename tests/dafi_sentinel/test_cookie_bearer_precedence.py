"""Tests for the cookie+Bearer precedence (PR-C.12, R2 med, RFC 6750).

PR-C.12 fixes a precedence footgun: when a request carries BOTH a
session cookie and an ``Authorization: Bearer`` header with
DIFFERENT tokens, the bearer wins (RFC 6750 §2 — the
``Authorization`` header is the explicit credential and the cookie
is incidental). The prior ``cookie-first`` precedence meant a stale
cookie could override a fresh bearer, which is the opposite of what
RFC 6750 prescribes and confusing for clients that mix transports.

This module pins the new precedence and the supporting contract:

* Bearer + cookie with different tokens → bearer wins.
* Bearer only → bearer is used.
* Cookie only → cookie is used.
* Neither → 401 with a descriptive error.
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
from dafi_sentinel.domain.models import Permission, Role
from dafi_sentinel.retrieval.contracts import InMemoryRetrievalIndex


def _build_app_and_login():
    users = InMemoryUserStore()
    users.add(
        "user-1",
        "Ada",
        "ada",
        "hunter2!",
        roles=(Role("analyst", permissions=(Permission("chart:request"),)),),
    )
    users.add(
        "user-2",
        "Bob",
        "bob",
        "another!",
        roles=(Role("analyst", permissions=(Permission("chart:request"),)),),
    )
    auth = AuthService(users=users, sessions=InMemorySessionStore())
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        retrieval_index=InMemoryRetrievalIndex(()),
    )
    app = create_workbench_app(auth=auth, workbench=workbench)
    return app, auth


def test_bearer_wins_when_both_cookie_and_bearer_present():
    """When both transports are present, the Bearer header is honored (RFC 6750)."""
    app, auth = _build_app_and_login()
    ada_session = auth.login("ada", "hunter2!")
    bob_session = auth.login("bob", "another!")
    with TestClient(app) as client:
        # Cookie carries ada's token; the bearer carries bob's token.
        # RFC 6750: the bearer wins.
        client.cookies.set("dafi_sentinel_session", ada_session.token)
        response = client.get(
            "/sessions/me",
            headers={"Authorization": f"Bearer {bob_session.token}"},
        )
    assert response.status_code == 200
    # The response body MUST reference bob (the bearer identity), not ada.
    assert response.json()["user_id"] == "user-2"


def test_cookie_used_when_bearer_absent():
    """Without an Authorization header, the cookie is the transport."""
    app, auth = _build_app_and_login()
    ada_session = auth.login("ada", "hunter2!")
    with TestClient(app) as client:
        client.cookies.set("dafi_sentinel_session", ada_session.token)
        response = client.get("/sessions/me")
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"


def test_bearer_used_when_cookie_absent():
    """Without a cookie, the Authorization header is the transport."""
    app, auth = _build_app_and_login()
    ada_session = auth.login("ada", "hunter2!")
    with TestClient(app) as client:
        response = client.get(
            "/sessions/me",
            headers={"Authorization": f"Bearer {ada_session.token}"},
        )
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"


def test_missing_both_transports_returns_401():
    """A request with no cookie and no bearer is rejected with 401."""
    app, _ = _build_app_and_login()
    with TestClient(app) as client:
        response = client.get("/sessions/me")
    assert response.status_code == 401
