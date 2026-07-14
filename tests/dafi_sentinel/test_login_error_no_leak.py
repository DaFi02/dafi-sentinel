"""Test that login error messages do not leak username existence (R3 F26).

The 4R review caught that an attacker could enumerate valid usernames
by inspecting the login error string: a wrong-password attempt on a
real account and a missing-user attempt returned distinguishable
messages (or distinct HTTP statuses). The contract is that BOTH
failure modes return the SAME 401 + ``invalid credentials`` body so
the API surface is identical whether the username exists or the
password is wrong.

The fixture exercises both paths through the FastAPI handler (the
public attack surface) and the ``AuthService.login`` helper (the
inner seam) so the contract is pinned on both layers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dafi_sentinel.api.app import create_workbench_app
from dafi_sentinel.api.auth import (
    AuthService,
    InMemorySessionStore,
    InMemoryUserStore,
    InvalidCredentialsError,
)
from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
)
from dafi_sentinel.domain.models import Permission, Role


def _seeded_app() -> tuple[TestClient, str, str]:
    """Build a fresh FastAPI app with one analyst and one maintainer."""
    analyst = Role(
        "analyst",
        permissions=(Permission("tool:search"), Permission("chart:request")),
    )
    maintainer = Role("maintainer", permissions=(Permission("tool:python"),))

    users = InMemoryUserStore()
    users.add("user-1", "Analyst", "ada", "hunter2!", roles=(analyst,))
    users.add("user-2", "Maintainer", "mike", "correct horse", roles=(maintainer,))

    auth = AuthService(users=users, sessions=InMemorySessionStore())
    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
    )
    app = create_workbench_app(auth=auth, workbench=workbench, cookie_secure=False)
    return TestClient(app), "ada", "hunter2!"


def test_login_error_message_does_not_leak_username_existence() -> None:
    """R3 F26: login errors must be identical for unknown user vs wrong password.

    The 4R review caught that an attacker could enumerate valid
    usernames by inspecting the login error string. The contract is
    that BOTH failure modes return the SAME 401 + ``invalid
    credentials`` body so the public API surface is identical
    whether the username exists or the password is wrong.
    """
    client, valid_username, valid_password = _seeded_app()

    # Wrong password on a real account.
    wrong_password = client.post(
        "/sessions",
        json={"username": valid_username, "password": "definitely-wrong"},
    )
    # Missing user account.
    unknown_user = client.post(
        "/sessions",
        json={"username": "ghost", "password": "anything"},
    )

    # The HTTP status MUST be identical (both 401).
    assert wrong_password.status_code == 401
    assert unknown_user.status_code == wrong_password.status_code, (
        f"unknown user and wrong password must share the same status; "
        f"got wrong={wrong_password.status_code} unknown={unknown_user.status_code}"
    )

    # The body detail MUST be identical: same wording, same shape.
    wrong_body = wrong_password.json()
    unknown_body = unknown_user.json()
    assert wrong_body == unknown_body, (
        f"unknown user and wrong password must return the SAME body so the API "
        f"does not leak username existence; got wrong={wrong_body} "
        f"unknown={unknown_body}"
    )
    # The body MUST NOT carry any username-specific field; a strict
    # equality assertion already enforces this. The contract is that
    # the body is exactly ``{"detail": "invalid credentials"}``.
    assert wrong_body == {"detail": "invalid credentials"}


def test_login_helper_raises_identical_error_for_unknown_user_and_wrong_password() -> None:
    """The AuthService.login helper must raise the same exception class + message.

    The endpoint test pins the public surface; this test pins the
    inner AuthService seam so a future helper (e.g., a CLI login
    command) cannot regress the contract.
    """
    users = InMemoryUserStore()
    analyst = Role(
        "analyst",
        permissions=(Permission("tool:search"), Permission("chart:request")),
    )
    users.add("user-1", "Analyst", "ada", "hunter2!", roles=(analyst,))

    service = AuthService(users=users, sessions=InMemorySessionStore())

    with pytest.raises(InvalidCredentialsError) as wrong_password_exc:
        service.login("ada", "definitely-wrong")

    with pytest.raises(InvalidCredentialsError) as unknown_user_exc:
        service.login("ghost", "anything")

    # Same exception class (already asserted by pytest.raises); the
    # error message MUST be identical so a future caller logging the
    # exception cannot leak which path fired.
    assert str(wrong_password_exc.value) == str(unknown_user_exc.value)
    assert str(wrong_password_exc.value) == "invalid credentials"


@pytest.mark.parametrize(
    "username, password",
    [
        ("ada", "definitely-wrong"),  # real user, wrong password
        ("ghost", "anything"),  # missing user
        ("GHOST", "anything"),  # case-folded missing user (case-insensitive lookup)
    ],
)
def test_login_rejects_varied_invalid_credentials_with_identical_payload(
    username: str, password: str
) -> None:
    """Triangulation: every invalid-credential case must return the SAME payload.

    The parametrized cases cover the real-user wrong-password path,
    the missing-user path, and a case-folded variant. The contract
    is identical 401 + ``invalid credentials`` across all of them so
    an attacker cannot enumerate usernames via timing or casing.
    The empty-password path is rejected by the Pydantic schema at
    the request-shape layer (422 with a validation error) and is
    covered by the schema-level tests, not by this contract.
    """
    client, _, _ = _seeded_app()

    response = client.post("/sessions", json={"username": username, "password": password})

    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "invalid credentials"}