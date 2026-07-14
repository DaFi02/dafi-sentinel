"""Authentication and session helpers for the PR5 workbench API.

PR1 only modeled the ``ActorRef``/``UserRef`` contracts; PR5 turns them into
a runnable, owned-session middleware that the FastAPI app uses to gate
every endpoint. Sessions are local tokens (no SSO, no third-party
identity provider) and every authenticated request must resolve to a
``UserRef`` whose ``id`` matches the resource owner.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from passlib.context import CryptContext

from dafi_sentinel.domain.models import ActorRef, Permission, Role, UserRef


_PASSWORD_CONTEXT = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plaintext: str) -> str:
    """Hash a password with argon2 (passlib default rounds)."""
    return _PASSWORD_CONTEXT.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored argon2 hash."""
    return _PASSWORD_CONTEXT.verify(plaintext, hashed)


@dataclass(frozen=True)
class StoredUser:
    """Internal record backing the in-memory user store."""

    user: UserRef
    password_hash: str


class UserStore(Protocol):
    """Contract the API uses to look up users."""

    def find_by_id(self, user_id: str) -> StoredUser | None: ...
    def find_by_username(self, username: str) -> StoredUser | None: ...
    def list_users(self) -> tuple[StoredUser, ...]: ...


@dataclass
class InMemoryUserStore:
    """Test-friendly user store keyed by user id and lowercase username."""

    _users: dict[str, StoredUser] = field(default_factory=dict)
    _usernames: dict[str, str] = field(default_factory=dict)

    def add(
        self,
        user_id: str,
        display_name: str,
        username: str,
        password: str,
        roles: tuple[Role, ...] = (),
    ) -> StoredUser:
        if user_id in self._users:
            raise ValueError(f"duplicate user id: {user_id}")
        username_key = username.lower()
        if username_key in self._usernames:
            raise ValueError(f"duplicate username: {username}")

        stored = StoredUser(
            user=UserRef(id=user_id, display_name=display_name, roles=roles),
            password_hash=hash_password(password),
        )
        self._users[user_id] = stored
        self._usernames[username_key] = user_id
        return stored

    def find_by_id(self, user_id: str) -> StoredUser | None:
        return self._users.get(user_id)

    def find_by_username(self, username: str) -> StoredUser | None:
        user_id = self._usernames.get(username.lower())
        if user_id is None:
            return None
        return self._users.get(user_id)

    def list_users(self) -> tuple[StoredUser, ...]:
        return tuple(self._users.values())


@dataclass(frozen=True)
class Session:
    """Active session linking a token to an authenticated user."""

    token: str
    user_id: str
    issued_at: datetime


class SessionStore(Protocol):
    """Contract the API uses to issue, validate, and revoke sessions."""

    def issue(self, user_id: str) -> Session: ...
    def resolve(self, token: str) -> Session | None: ...
    def revoke(self, token: str) -> bool: ...


@dataclass
class InMemorySessionStore:
    """In-memory session store used by tests and the reference FastAPI app."""

    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _by_token: dict[str, Session] = field(default_factory=dict)
    _by_user: dict[str, str] = field(default_factory=dict)

    def issue(self, user_id: str) -> Session:
        token = secrets.token_urlsafe(32)
        session = Session(token=token, user_id=user_id, issued_at=self.clock())
        self._by_token[token] = session
        # Last-issued-wins keeps the surface small while still rejecting stale tokens on logout.
        self._by_user[user_id] = token
        return session

    def resolve(self, token: str) -> Session | None:
        session = self._by_token.get(token)
        if session is None:
            return None
        # Invalidate a session whose token no longer matches the active token for the user.
        active = self._by_user.get(session.user_id)
        if active != token:
            self._by_token.pop(token, None)
            return None
        return session

    def revoke(self, token: str) -> bool:
        session = self._by_token.pop(token, None)
        if session is None:
            return False
        if self._by_user.get(session.user_id) == token:
            self._by_user.pop(session.user_id, None)
        return True


class InvalidCredentialsError(Exception):
    """Raised when authentication fails (bad username or password)."""


@dataclass
class AuthService:
    """Coordinates user lookup, password verification, and session issue/revoke."""

    users: UserStore
    sessions: SessionStore
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def login(self, username: str, password: str) -> Session:
        stored = self.users.find_by_username(username)
        if stored is None or not verify_password(password, stored.password_hash):
            raise InvalidCredentialsError("invalid credentials")
        return self.sessions.issue(stored.user.id)

    def logout(self, token: str) -> bool:
        return self.sessions.revoke(token)

    def resolve_session(self, token: str) -> tuple[Session, StoredUser] | None:
        session = self.sessions.resolve(token)
        if session is None:
            return None
        stored = self.users.find_by_id(session.user_id)
        if stored is None:
            return None
        return session, stored

    def actor_for(self, user: UserRef) -> ActorRef:
        """Project a :class:`UserRef` to the :class:`ActorRef` the API uses in audits."""
        return ActorRef(id=user.id, kind="user")


def require_owner(actor: UserRef, owner_id: str) -> None:
    """Raise :class:`PermissionError` if the actor does not own the resource.

    The API uses this helper to keep ownership checks declarative; the
    FastAPI dependency layer catches the error and turns it into a 403.
    """
    if actor.id != owner_id:
        raise PermissionError(f"actor {actor.id!r} does not own resource {owner_id!r}")


def roles_of(user: UserRef) -> tuple[str, ...]:
    """Return the role names attached to a user (used for audit context)."""
    return tuple(role.name for role in user.roles)


def permissions_of(user: UserRef) -> tuple[Permission, ...]:
    """Flatten the permissions carried by the user's roles."""
    flat: list[Permission] = []
    for role in user.roles:
        flat.extend(role.permissions)
    return tuple(flat)
