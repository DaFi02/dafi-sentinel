"""Tests for the deprecation warning on DELETE /sessions/{token} (PR-C.11, R4 high#7).

PR-C.11 marks the bearer-only logout path as deprecated. The
dashboard has migrated to ``DELETE /sessions/me`` (cookie path);
non-browser clients (curl, CLI) can keep using ``DELETE
/sessions/{token}`` for now, but the response carries a
``Deprecation`` and ``Sunset`` header so the client can plan a
migration. The route is still functional — only the headers are
added. The fix is non-breaking.
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
    auth = AuthService(users=users, sessions=InMemorySessionStore())
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        retrieval_index=InMemoryRetrievalIndex(()),
    )
    app = create_workbench_app(auth=auth, workbench=workbench)
    return app, auth


def test_delete_token_route_carries_deprecation_header():
    """DELETE /sessions/{token} sets Deprecation and Sunset response headers."""
    app, auth = _build_app_and_login()
    session = auth.login("ada", "hunter2!")
    with TestClient(app) as client:
        response = client.delete(
            f"/sessions/{session.token}",
            headers={"Authorization": f"Bearer {session.token}"},
        )
    assert response.status_code == 204
    assert response.headers.get("deprecation") == "true"
    # Sunset is the planned-removal date (RFC 8594).
    assert "sunset" in {k.lower() for k in response.headers}


def test_delete_me_route_does_not_carry_deprecation_header():
    """The cookie path is the migration target; no deprecation header on /sessions/me."""
    app, auth = _build_app_and_login()
    session = auth.login("ada", "hunter2!")
    with TestClient(app) as client:
        # /sessions/me uses the cookie transport; the test cookie
        # plugin is happy with a synthetic cookie value matching the
        # session token so we can exercise the route without going
        # through the cookie path.
        client.cookies.set("dafi_sentinel_session", session.token)
        response = client.delete("/sessions/me")
    # /sessions/me is the migration target: NO deprecation header.
    assert response.status_code == 204
    assert "deprecation" not in {k.lower() for k in response.headers}
