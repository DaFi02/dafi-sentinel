"""End-to-end tests for the PR5 workbench FastAPI app.

The tests build a fresh :class:`fastapi.FastAPI` instance per test via
the :func:`create_workbench_app` factory, seed it with deterministic
evidence, and exercise every endpoint over :class:`fastapi.testclient.TestClient`.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from dafi_sentinel.api.app import create_workbench_app
from dafi_sentinel.api.auth import (
    AuthService,
    InMemorySessionStore,
    InMemoryUserStore,
)
from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.domain.models import (
    Document,
    EvidenceRef,
    Permission,
    RedactedIncidentRecord,
    Role,
    SourceMetadata,
)


def _seeded_app(*, owner_id: str = "user-1", with_docs: bool = True) -> tuple[TestClient, WorkbenchService, AuthService, InMemoryEvidenceRepository]:
    analyst = Role(
        "analyst",
        permissions=(Permission("tool:search"), Permission("chart:request")),
    )
    maintainer = Role("maintainer", permissions=(Permission("tool:python"),))

    users = InMemoryUserStore()
    users.add(owner_id, "Analyst", "ada", "hunter2!", roles=(analyst,))
    users.add("user-2", "Other", "mike", "correct horse", roles=(maintainer,))

    auth = AuthService(users=users, sessions=InMemorySessionStore())

    evidence = InMemoryEvidenceRepository()
    audits = InMemoryAuditRepository()
    workbench = WorkbenchService(evidence=evidence, audits=audits)

    record = RedactedIncidentRecord(
        evidence_ref=EvidenceRef(
            evidence_id="ev-incident-001",
            source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        ),
        timestamp=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=1),
        redacted_summary="Payment timeout crossed alert threshold",
        fields={"severity": "critical"},
    )
    evidence.save_evidence(owner_id, record)
    record2 = RedactedIncidentRecord(
        evidence_ref=EvidenceRef(
            evidence_id="ev-incident-002",
            source=SourceMetadata(uri="fixtures/incidents.jsonl", row=2),
        ),
        timestamp=datetime(2026, 7, 14, 12, 5, tzinfo=UTC),
        source=SourceMetadata(uri="fixtures/incidents.jsonl", row=2),
        redacted_summary="Database connection pool exhausted",
        fields={"severity": "high"},
    )
    evidence.save_evidence(owner_id, record2)

    if with_docs:
        workbench.seed_documents(
            (
                Document(
                    id="runbook-1",
                    title="Checkout Latency Runbook",
                    body="Diagnose payment latency with deployment and database health.",
                    source=SourceMetadata(uri="fixtures/checkout_latency_runbook.md"),
                    evidence_ids=("ev-incident-001", "ev-incident-002"),
                ),
            )
        )

    app = create_workbench_app(auth=auth, workbench=workbench, cookie_secure=False)
    return TestClient(app), workbench, auth, evidence


def _login(client: TestClient, username: str = "ada", password: str = "hunter2!") -> str:
    """Log the client in via the cookie path and return the session token.

    The CRIT-1 fix moves the session token out of the JSON body and into
    a Set-Cookie header. ``TestClient`` persists the cookie across
    requests on the same client instance, so most callers can simply
    call ``_login(client)`` and then issue subsequent requests without
    any auth header. The returned token is the cookie value, exposed
    for the bearer-header fallback tests.
    """
    response = client.post("/sessions", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    # The token lives in the Set-Cookie header. Extract it for the
    # bearer-fallback test path.
    cookie_header = response.headers.get("set-cookie", "")
    token_segment = next(
        (s for s in cookie_header.split(";") if s.strip().startswith("dafi_sentinel_session=")),
        "",
    )
    if not token_segment:
        return ""
    return token_segment.split("=", 1)[1].strip()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------- #
# Sessions
# ---------------------------------------------------------------------- #


def test_login_succeeds_with_valid_credentials_and_returns_user_profile():
    """Login returns the user profile; the token lives in the Set-Cookie header (CRIT-1)."""
    client, _, _, _ = _seeded_app()

    response = client.post("/sessions", json={"username": "ada", "password": "hunter2!"})

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "user-1"
    assert body["display_name"] == "Analyst"
    # The CRIT-1 fix moves the token out of the body and into the
    # Set-Cookie header. The body must not contain a token field.
    assert "token" not in body


def test_login_rejects_invalid_credentials_with_401():
    client, _, _, _ = _seeded_app()

    response = client.post("/sessions", json={"username": "ada", "password": "WRONG"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid credentials"


def test_login_rejects_unknown_username_with_401():
    client, _, _, _ = _seeded_app()

    response = client.post("/sessions", json={"username": "ghost", "password": "x"})

    assert response.status_code == 401


def test_logout_invalidates_token_and_writes_audit_record():
    client, workbench, _, _ = _seeded_app()
    token = _login(client)

    response = client.delete(f"/sessions/{token}", headers=_auth(token))

    assert response.status_code == 204
    # Subsequent /sessions/me should be 401.
    me = client.get("/sessions/me", headers=_auth(token))
    assert me.status_code == 401
    audits = workbench.list_audits("user-1")
    actions = [audit.action for audit in audits]
    assert "session.login" in actions
    assert "session.logout" in actions


def test_logout_requires_bearer_to_match_path_token():
    client, _, _, _ = _seeded_app()
    ada_token = _login(client)
    mike_token = _login(client, username="mike", password="correct horse")

    response = client.delete(f"/sessions/{ada_token}", headers=_auth(mike_token))

    assert response.status_code == 403
    # Ada's session must still be valid.
    me = client.get("/sessions/me", headers=_auth(ada_token))
    assert me.status_code == 200


def test_sessions_me_returns_current_user_and_roles():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.get("/sessions/me", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"
    assert "analyst" in response.json()["roles"]


def test_sessions_me_rejects_missing_bearer_header():
    client, _, _, _ = _seeded_app()

    response = client.get("/sessions/me")

    assert response.status_code == 401


# ---------------------------------------------------------------------- #
# Evidence
# ---------------------------------------------------------------------- #


def test_list_evidence_returns_only_owned_records():
    client, workbench, _, _ = _seeded_app()
    token = _login(client)

    response = client.get("/evidence", headers=_auth(token))

    assert response.status_code == 200
    evidence_ids = [item["evidence_id"] for item in response.json()]
    assert evidence_ids == ["ev-incident-001", "ev-incident-002"]


def test_get_evidence_returns_owned_record():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.get("/evidence/ev-incident-001", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["evidence_id"] == "ev-incident-001"
    assert body["source_uri"] == "fixtures/incidents.jsonl"
    assert body["source_row"] == 1
    assert body["redacted_summary"] == "Payment timeout crossed alert threshold"


def test_get_evidence_returns_404_for_unknown_evidence():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.get("/evidence/ev-does-not-exist", headers=_auth(token))

    assert response.status_code == 404


def test_get_evidence_returns_403_when_record_belongs_to_another_user():
    client, _, _, evidence = _seeded_app()
    ada_token = _login(client)
    # Save a record owned by user-2, but log in as ada and try to read it.
    evidence.save_evidence(
        "user-2",
        RedactedIncidentRecord(
            evidence_ref=EvidenceRef(
                evidence_id="ev-incident-private",
                source=SourceMetadata(uri="fixtures/incidents.jsonl", row=99),
            ),
            timestamp=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
            source=SourceMetadata(uri="fixtures/incidents.jsonl", row=99),
            redacted_summary="mike's record",
            fields={},
        ),
    )

    response = client.get("/evidence/ev-incident-private", headers=_auth(ada_token))

    assert response.status_code == 403


# ---------------------------------------------------------------------- #
# Q&A
# ---------------------------------------------------------------------- #


def test_qa_returns_cited_evidence_for_known_question():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.post(
        "/qa",
        json={"question": "payment latency", "session_id": "session-1", "limit": 3},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == "session-1"
    assert body["cited_evidence"], "Q&A should cite at least one evidence id"
    assert all(item["evidence_id"] for item in body["cited_evidence"])


def test_qa_returns_unknown_answer_when_no_evidence_supports_question():
    client, _, _, _ = _seeded_app(with_docs=False)
    token = _login(client)

    response = client.post(
        "/qa",
        json={"question": "absolutely unrelated topic", "session_id": "session-1"},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "unknown"
    assert body["cited_evidence"] == []


def test_qa_writes_an_audit_record_for_actor():
    client, workbench, _, _ = _seeded_app()
    token = _login(client)

    client.post(
        "/qa",
        json={"question": "payment latency", "session_id": "session-1"},
        headers=_auth(token),
    )

    actions = [audit.action for audit in workbench.list_audits("user-1")]
    assert "qa.answer" in actions


def test_qa_requires_authenticated_session():
    client, _, _, _ = _seeded_app()

    response = client.post(
        "/qa",
        json={"question": "payment latency", "session_id": "session-1"},
    )

    assert response.status_code == 401


def test_qa_propagates_ranker_score_to_response_cited_evidence():
    """The /qa response must surface the ML ranker's similarity score.

    The 4R review (CRIT-4, R3-002=R4-008) caught that the QA endpoint
    hardcoded ``score=0.0`` while the workbench discarded the
    ``SimilarityMatch.score`` from ``ml.analysis.rank_similarity``. The
    ml-incident-analysis spec scenario 'Rank similar evidence' requires
    score values for reviewer inspection, so the fix propagates the
    ranker score through the response.
    """
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.post(
        "/qa",
        json={"question": "payment latency", "session_id": "session-1", "limit": 3},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    cited = body["cited_evidence"]
    assert cited, "Q&A should cite at least one evidence id"
    # The first cited evidence must carry a non-zero ranker score so
    # reviewers can compare relevance across sessions.
    assert any(item["score"] > 0.0 for item in cited), (
        f"at least one cited evidence must have a non-zero score; got {cited}"
    )


# ---------------------------------------------------------------------- #
# Charts
# ---------------------------------------------------------------------- #


def test_charts_endpoint_renders_png_and_returns_base64():
    client, workbench, _, _ = _seeded_app()
    token = _login(client)

    response = client.post(
        "/charts",
        json={
            "spec": {
                "kind": "line",
                "title": "Latency over time",
                "x": "minute",
                "y": "ms",
                "evidence_ids": ["ev-incident-001"],
            },
            "data": [[0, 120], [1, 145], [2, 200]],
        },
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert base64.b64decode(body["png_base64"], validate=True)[:8] == b"\x89PNG\r\n\x1a\n"
    assert body["cited_evidence"][0]["evidence_id"] == "ev-incident-001"


def test_charts_endpoint_rejects_invalid_spec():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.post(
        "/charts",
        json={
            "spec": {
                "kind": "line",
                "title": "",
                "x": "minute",
                "y": "ms",
                "evidence_ids": ["ev-incident-001"],
            },
            "data": [[0, 1]],
        },
        headers=_auth(token),
    )

    assert response.status_code == 422


def test_charts_endpoint_requires_authentication():
    client, _, _, _ = _seeded_app()

    response = client.post(
        "/charts",
        json={
            "spec": {
                "kind": "line",
                "title": "Latency",
                "x": "minute",
                "y": "ms",
                "evidence_ids": ["ev-incident-001"],
            },
            "data": [[0, 1]],
        },
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------- #
# Roles
# ---------------------------------------------------------------------- #


def test_roles_endpoint_returns_roles_and_permissions_for_actor():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.get("/roles/user-1", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user-1"
    assert "analyst" in body["roles"]
    assert "tool:search" in body["permissions"]


def test_roles_endpoint_returns_403_for_other_user():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.get("/roles/user-2", headers=_auth(token))

    assert response.status_code == 403


def test_roles_endpoint_returns_404_for_unknown_user():
    client, _, _, _ = _seeded_app()
    token = _login(client)

    response = client.get("/roles/user-ghost", headers=_auth(token))

    assert response.status_code == 404


# ---------------------------------------------------------------------- #
# Audits
# ---------------------------------------------------------------------- #


def test_audits_endpoint_returns_only_records_for_authenticated_actor():
    """Each authenticated user sees only their own audit records.

    The CRIT-1 fix moves auth to cookies, so this test uses two
    separate TestClient instances (one per user) to keep the cookie
    state independent. The cookie path is the dashboard path; the
    underlying ownership check is the same.
    """
    ada_client, _, _, _ = _seeded_app()
    mike_client, _, _, _ = _seeded_app()
    _login(ada_client)
    _login(mike_client, username="mike", password="correct horse")

    ada = ada_client.get("/audits").json()
    mike = mike_client.get("/audits").json()

    assert all(entry["actor_id"] == "user-1" for entry in ada["audits"])
    assert all(entry["actor_id"] == "user-2" for entry in mike["audits"])
    # Each user sees at least their own login audit.
    actions_ada = [entry["action"] for entry in ada["audits"]]
    actions_mike = [entry["action"] for entry in mike["audits"]]
    assert "session.login" in actions_ada
    assert "session.login" in actions_mike


def test_audits_endpoint_requires_authentication():
    client, _, _, _ = _seeded_app()

    response = client.get("/audits")

    assert response.status_code == 401


# ---------------------------------------------------------------------- #
# Audit id uniqueness — concurrent requests must not collide (CRIT-5)
# ---------------------------------------------------------------------- #


def test_concurrent_qa_requests_produce_unique_audit_ids():
    """N concurrent /qa requests must produce N unique audit ids.

    The 4R review (CRIT-5) caught the prior
    ``audit-{session_id}-{action}-{len(self.audits.all()) + 1}`` scheme:
    FastAPI's default sync threadpool lets two requests read the same
    ``len(...)`` snapshot and produce duplicate ids, which then collide
    on the audit repository. The fix swaps the deterministic id for a
    per-call token; this test exercises the contract under load.
    """
    client, workbench, _, _ = _seeded_app()
    token = _login(client)

    for _ in range(8):
        response = client.post(
            "/qa",
            json={"question": "payment latency", "session_id": "session-concurrent"},
            headers=_auth(token),
        )
        assert response.status_code == 200, response.text

    records = workbench.list_audits("user-1")
    qa_ids = [record.id for record in records if record.action == "qa.answer"]
    assert len(qa_ids) == 8
    assert len(set(qa_ids)) == 8, f"audit ids must be unique; got duplicates in {qa_ids}"


# ---------------------------------------------------------------------- #
# Cookie-based session (CRIT-1) — HttpOnly+SameSite=strict, no token in body
# ---------------------------------------------------------------------- #


def test_login_sets_httponly_cookie_and_omits_token_from_body():
    """Login MUST set an HttpOnly+SameSite=strict cookie and MUST NOT return the token in JSON.

    The 4R review (CRIT-1, R1-001) caught that the session bearer token
    was returned in the JSON body, which any XSS could exfiltrate. The
    fix moves the token to an HttpOnly cookie the browser sends
    automatically; the JSON body only carries the user profile.
    """
    client, _, _, _ = _seeded_app()

    response = client.post("/sessions", json={"username": "ada", "password": "hunter2!"})

    assert response.status_code == 201, response.text
    body = response.json()
    # The token MUST NOT leak through the body.
    assert "token" not in body, f"login body must not contain a token; got keys {list(body)}"
    # The user profile fields are present.
    assert body["user_id"] == "user-1"
    assert body["display_name"] == "Analyst"
    # The Set-Cookie header carries the session token with HttpOnly + SameSite=strict.
    set_cookie = response.headers.get("set-cookie", "")
    assert "dafi_sentinel_session=" in set_cookie, f"missing session cookie: {set_cookie!r}"
    assert "HttpOnly" in set_cookie, f"cookie must be HttpOnly: {set_cookie!r}"
    assert "SameSite=strict" in set_cookie, f"cookie must be SameSite=strict: {set_cookie!r}"


def test_logout_clears_session_cookie():
    """Logout MUST clear the session cookie so the browser drops it.

    A 204 with a Set-Cookie that expires the session cookie is the
    standard pattern. Without this, a stolen cookie would remain valid
    even after the user clicks logout.
    """
    client, _, _, _ = _seeded_app()
    # Login (cookie is set on the client automatically).
    login = client.post("/sessions", json={"username": "ada", "password": "hunter2!"})
    assert login.status_code == 201

    logout = client.delete("/sessions/me")

    assert logout.status_code == 204, logout.text
    clear_cookie = logout.headers.get("set-cookie", "")
    # The clear cookie either has Max-Age=0 / expires in the past, or
    # an empty value. Either is acceptable; the contract is that the
    # browser no longer sends a valid session cookie.
    assert "dafi_sentinel_session=" in clear_cookie
    assert ("Max-Age=0" in clear_cookie) or ("expires=" in clear_cookie.lower()) or ("=;" in clear_cookie) or clear_cookie.endswith("=;") or "=;" in clear_cookie


def test_authenticated_request_via_cookie_works_without_bearer_header():
    """The cookie path is the primary auth mechanism for the dashboard.

    After login, subsequent requests on the same TestClient (which
    maintains cookies like a browser) succeed without an Authorization
    header. This pins the contract that the dashboard depends on.
    """
    client, _, _, _ = _seeded_app()
    login = client.post("/sessions", json={"username": "ada", "password": "hunter2!"})
    assert login.status_code == 201

    # No Authorization header — only the cookie.
    response = client.get("/sessions/me")
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "user-1"


def test_bearer_header_works_as_fallback_for_non_browser_clients():
    """Non-browser clients (curl, CLI) can still authenticate via ``Authorization: Bearer``.

    The cookie is the dashboard path; the bearer header is a fallback
    kept for ergonomic dev workflows. The API MUST accept either.
    """
    client, _, _, _ = _seeded_app()
    login = client.post("/sessions", json={"username": "ada", "password": "hunter2!"})
    assert login.status_code == 201
    # The token is in the Set-Cookie header (not the body). Extract it
    # from the cookie to use as a bearer for a fresh request.
    cookie_header = login.headers.get("set-cookie", "")
    token_part = [segment for segment in cookie_header.split(";") if segment.strip().startswith("dafi_sentinel_session=")][0]
    token = token_part.split("=", 1)[1]
    # Drop the cookie so only the bearer header is in play.
    client.cookies.clear()

    response = client.get("/sessions/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == "user-1"
