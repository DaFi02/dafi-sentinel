"""Tests for the PR5 authentication and session helpers.

These tests pin the contract that the FastAPI app depends on:

* Passwords are stored as argon2 hashes and verified correctly.
* Sessions are bound to a user and survive multiple resolves.
* A revoked session token no longer resolves.
* The last-issued-token policy invalidates older tokens for the same user.
* Ownership checks raise :class:`PermissionError` for mismatches.
"""

from datetime import UTC, datetime

import pytest

from dafi_sentinel.api.auth import (
    AuthService,
    InMemorySessionStore,
    InMemoryUserStore,
    InvalidCredentialsError,
    require_owner,
)
from dafi_sentinel.domain.models import Permission, Role, UserRef


def _user_store() -> InMemoryUserStore:
    store = InMemoryUserStore()
    analyst = Role(
        "analyst",
        permissions=(Permission("tool:search"), Permission("chart:request")),
    )
    maintainer = Role("maintainer", permissions=(Permission("tool:python"),))
    store.add("user-1", "Analyst", "ada", "hunter2!", roles=(analyst,))
    store.add("user-2", "Maintainer", "mike", "correct horse", roles=(maintainer,))
    return store


def test_passwords_are_hashed_and_verified_independently_of_plaintext():
    store = _user_store()
    stored = store.find_by_username("ada")
    assert stored is not None
    assert stored.password_hash != "hunter2!"
    assert stored.password_hash.startswith("$argon2")
    assert stored.user.display_name == "Analyst"


def test_login_with_valid_credentials_issues_a_session_bound_to_user_id():
    service = AuthService(users=_user_store(), sessions=InMemorySessionStore())

    session = service.login("ada", "hunter2!")

    assert session.user_id == "user-1"
    resolved = service.resolve_session(session.token)
    assert resolved is not None
    _, stored = resolved
    assert stored.user.id == "user-1"


def test_login_with_invalid_password_raises_invalid_credentials_error():
    service = AuthService(users=_user_store(), sessions=InMemorySessionStore())

    with pytest.raises(InvalidCredentialsError):
        service.login("ada", "wrong-password")


def test_login_with_unknown_username_raises_invalid_credentials_error():
    service = AuthService(users=_user_store(), sessions=InMemorySessionStore())

    with pytest.raises(InvalidCredentialsError):
        service.login("ghost", "anything")


def test_logout_invalidates_the_session_token():
    service = AuthService(users=_user_store(), sessions=InMemorySessionStore())
    session = service.login("ada", "hunter2!")

    assert service.logout(session.token) is True
    assert service.resolve_session(session.token) is None
    # A second logout on the same token is a no-op, not an error.
    assert service.logout(session.token) is False


def test_re_issuing_a_session_for_the_same_user_invalidates_the_older_token():
    sessions = InMemorySessionStore(
        clock=lambda: datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    )
    service = AuthService(users=_user_store(), sessions=sessions)

    first = service.login("ada", "hunter2!")
    second = service.login("ada", "hunter2!")

    assert first.token != second.token
    assert service.resolve_session(first.token) is None
    assert service.resolve_session(second.token) is not None


def test_resolve_session_returns_none_when_user_record_disappears():
    service = AuthService(users=_user_store(), sessions=InMemorySessionStore())
    session = service.login("ada", "hunter2!")

    # Replace the user store with an empty one to simulate a deleted account.
    service.users = InMemoryUserStore()

    assert service.resolve_session(session.token) is None


def test_require_owner_passes_when_actor_matches_owner():
    user = UserRef(id="user-1", display_name="Ada")
    require_owner(user, "user-1")  # must not raise


def test_require_owner_raises_permission_error_for_mismatch():
    user = UserRef(id="user-1", display_name="Ada")
    with pytest.raises(PermissionError):
        require_owner(user, "user-2")


def test_user_store_rejects_duplicate_ids_and_usernames():
    store = InMemoryUserStore()
    store.add("user-1", "Ada", "ada", "hunter2!")

    with pytest.raises(ValueError):
        store.add("user-1", "Other Ada", "ada2", "x")

    with pytest.raises(ValueError):
        store.add("user-2", "Other Ada", "ada", "x")


def test_username_lookup_is_case_insensitive():
    store = _user_store()
    stored = store.find_by_username("ADA")
    assert stored is not None
    assert stored.user.id == "user-1"
