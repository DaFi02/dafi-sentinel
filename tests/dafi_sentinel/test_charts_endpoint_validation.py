"""Endpoint-level parametrized tests for the ChartValidationError handler (R3 F3).

The 4R review caught that :class:`ChartValidationError` raised by the
chart-spec validator was bubbling up as an unhandled exception (HTTP
500) instead of being mapped to a structured 422 response. The fix
adds an ``app.exception_handler(ChartValidationError)`` in
``dafi_sentinel.api.app``; this module pins the contract from the
outside in.

The Pydantic schema for ``ChartSpecPayload`` already rejects an empty
``title`` at the request-validation layer (so that case was always
422), but the empty / blank ``evidence_ids`` and blank axis fields
were NOT covered by the Pydantic validators and used to reach the
domain validator — which then surfaced as a 500. This test exercises
the cases the schema leaves to the domain validator.
"""

from __future__ import annotations

from typing import Any

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
from dafi_sentinel.domain.models import Permission, Role


def _seeded_app() -> tuple[TestClient, str]:
    analyst = Role(
        "analyst",
        permissions=(Permission("tool:search"), Permission("chart:request")),
    )
    users = InMemoryUserStore()
    users.add("user-1", "Analyst", "ada", "hunter2!", roles=(analyst,))

    auth = AuthService(users=users, sessions=InMemorySessionStore())
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
    )
    app = create_workbench_app(auth=auth, workbench=workbench, cookie_secure=False)
    client = TestClient(app)

    login = client.post("/sessions", json={"username": "ada", "password": "hunter2!"})
    assert login.status_code == 201, login.text
    token_segment = next(
        (s for s in login.headers.get("set-cookie", "").split(";") if s.strip().startswith("dafi_sentinel_session=")),
        "",
    )
    token = token_segment.split("=", 1)[1].strip() if token_segment else ""
    return client, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _build_payload(spec_overrides: dict[str, Any]) -> dict[str, Any]:
    spec = {
        "kind": "line",
        "title": "Latency over time",
        "x": "minute",
        "y": "ms",
        "evidence_ids": ["ev-incident-001"],
    }
    spec.update(spec_overrides)
    return {"spec": spec, "data": [[0, 1]]}


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"evidence_ids": []}, "evidence_ids"),
        ({"evidence_ids": [""]}, "evidence_ids"),
        ({"x": ""}, "x"),
    ],
)
def test_charts_endpoint_rejects_invalid_spec(overrides: dict[str, Any], field: str) -> None:
    """The /charts endpoint must reject invalid specs with a 422 payload.

    R3 F3: the 4R review caught that ``ChartValidationError`` raised
    by the validator was bubbling up as a 500. The Pydantic schema
    covers ``title`` (and the request shape), but the domain validator
    is the source of truth for ``evidence_ids`` and ``x`` / ``y`` axis
    fields. The fix adds an ``app.exception_handler(ChartValidationError)``
    that maps the error to a structured 422 so the dashboard can
    surface a useful error message instead of an opaque 500.
    """
    client, token = _seeded_app()
    payload = _build_payload(overrides)

    response = client.post("/charts", json=payload, headers=_auth(token))

    assert response.status_code == 422, response.text
    body = response.json()
    # The handler must surface which field failed; the validator
    # exposes the field name on the exception instance.
    detail = body.get("detail", {})
    assert detail.get("field") == field, (
        f"the 422 payload must identify the failing field; got {body}"
    )
    assert detail.get("reason"), f"the 422 payload must carry a reason; got {body}"