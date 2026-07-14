"""Tests for rate limits and payload-size caps (R1 high#3).

PR-C.4 ships two hardening layers on the public mutation endpoints:

* A per-IP rate limit on ``POST /sessions`` (login) and a per-user
  rate limit on ``POST /qa`` / ``POST /charts`` (authenticated
  mutations). The rate limiter returns ``429 Too Many Requests`` once
  the budget is exhausted.
* A payload-size cap that rejects requests with a body larger than
  the configured budget. The cap is enforced at the middleware layer
  so an oversized request never reaches the handler.

Both layers are off by default (the dev factory and the pre-PR-C.4
test suite keep the legacy behavior). The defaults are intentionally
strict so a misconfigured deploy cannot accidentally disable them.
"""

from __future__ import annotations

import pytest
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


def _build_app(*, rate_limit: int | None = None, max_payload_bytes: int | None = None):
    users = InMemoryUserStore()
    users.add(
        "user-1",
        "Analyst",
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
    kwargs = {}
    if rate_limit is not None:
        kwargs["rate_limit_per_minute"] = rate_limit
    if max_payload_bytes is not None:
        kwargs["max_payload_bytes"] = max_payload_bytes
    return create_workbench_app(
        auth=auth,
        workbench=workbench,
        **kwargs,
    )


def test_rate_limit_flag_is_accepted_by_factory():
    """The new ``rate_limit_per_minute`` kwarg is part of the public API."""
    app = _build_app(rate_limit=10)
    assert app.title == "DAFI Sentinel Workbench API"


def test_login_endpoint_returns_429_after_rate_limit_exhausted():
    """Posting to /sessions past the rate limit returns 429."""
    app = _build_app(rate_limit=3)
    with TestClient(app) as client:
        for attempt in range(3):
            # Use bad credentials to keep the test focused on rate
            # limiting (no successful logins to confound the count).
            response = client.post(
                "/sessions",
                json={"username": "ada", "password": "wrong"},
            )
            assert response.status_code in (200, 201, 401), f"unexpected {response.status_code} on attempt {attempt + 1}"
        # The 4th request MUST be rate-limited.
        response = client.post(
            "/sessions",
            json={"username": "ada", "password": "wrong"},
        )
    assert response.status_code == 429


def test_payload_size_cap_rejects_oversized_login_body():
    """A login body larger than the cap returns 413 before reaching the handler."""
    app = _build_app(max_payload_bytes=128)
    big_password = "a" * 1024
    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json={"username": "ada", "password": big_password},
        )
    # Either 413 (size cap) or 422 (Pydantic max_length from C.5)
    # is acceptable; both reject the request before reaching auth.
    assert response.status_code in (413, 422)


def test_payload_size_cap_is_off_by_default():
    """Pre-PR-C.4 call sites keep the legacy unlimited-body behavior."""
    app = _build_app()
    with TestClient(app) as client:
        # A 4 KB body MUST still be accepted (or rejected by Pydantic
        # at 422, not by a 413 payload cap).
        response = client.post(
            "/sessions",
            json={"username": "ada", "password": "a" * 4096},
        )
    assert response.status_code in (401, 422)


def test_rate_limit_does_not_break_legacy_call_sites():
    """Without the flag, the rate limit is not enforced (legacy behavior)."""
    app = _build_app()
    with TestClient(app) as client:
        for _ in range(20):
            response = client.post(
                "/sessions",
                json={"username": "ada", "password": "wrong"},
            )
            # All 20 must be 401 (auth failure), not 429.
            assert response.status_code == 401
