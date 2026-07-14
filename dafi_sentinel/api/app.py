"""FastAPI application factory for the PR5 workbench API.

The factory wires the deterministic services to a small set of HTTP
endpoints:

* ``POST /sessions`` (login) and ``DELETE /sessions/{token}`` (logout)
* ``GET /sessions/me`` (current user)
* ``GET /evidence/{evidence_id}`` and ``GET /evidence`` (owned list)
* ``POST /qa`` (RAG Q&A)
* ``POST /charts`` (renderer delegation)
* ``GET /roles/{user_id}`` (role lookup)
* ``GET /audits`` (actor-scoped audit list)

All endpoints enforce session ownership through the
:mod:`dafi_sentinel.api.auth` helpers; every stateful action writes an
``AuditRecord`` through the ``AuditRepository`` contract.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from dafi_sentinel.api.auth import (
    AuthService,
    InvalidCredentialsError,
    Session,
    StoredUser,
    hash_session_id,
    require_owner,
)
from dafi_sentinel.api.schemas import (
    AuditEntryResponse,
    AuditsResponse,
    ChartRequest,
    ChartResponse,
    ChartSpecPayload,
    CitedEvidence,
    EvidenceResponse,
    LoginRequest,
    QAResponse,
    QuestionRequest,
    RoleResponse,
    SessionResponse,
)
from dafi_sentinel.charts.validation import ChartValidationError
from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
    png_to_base64,
)
from dafi_sentinel.domain.models import ActorRef, ChartSpec, UserRef
from dafi_sentinel.security.policy import SecurityGate


# Default sweeper interval (seconds) for the FastAPI lifespan task.
# PR-C.2 ships the lifespan; operators that want a different cadence
# can pass ``sweeper_interval_seconds`` to ``create_workbench_app``.
DEFAULT_SWEEPER_INTERVAL_SECONDS = 60


# PR-C.3 (R1 high#4): the security middleware ships with conservative
# defaults so a misconfigured deploy cannot accidentally leave the
# middleware disabled. The defaults match the values the 4R review
# flagged as the production-readiness floor.
DEFAULT_SECURITY_ALLOWED_HOSTS: tuple[str, ...] = ("localhost", "127.0.0.1")
DEFAULT_SECURITY_CORS_ORIGINS: tuple[str, ...] = ()
DEFAULT_HSTS_MAX_AGE_SECONDS = 60 * 60 * 24 * 365  # 1 year, conservative default


def create_workbench_app(
    *,
    auth: AuthService,
    workbench: WorkbenchService,
    cookie_secure: bool = True,
    cookie_name: str = "dafi_sentinel_session",
    gate: SecurityGate | None = None,
    sweep_graph: Callable[[], Any] | None = None,
    sweeper_interval_seconds: float = DEFAULT_SWEEPER_INTERVAL_SECONDS,
    enable_security_middleware: bool = False,
    security_allowed_hosts: tuple[str, ...] = DEFAULT_SECURITY_ALLOWED_HOSTS,
    security_cors_origins: tuple[str, ...] = DEFAULT_SECURITY_CORS_ORIGINS,
    hsts_max_age_seconds: int = DEFAULT_HSTS_MAX_AGE_SECONDS,
    rate_limit_per_minute: int | None = None,
    max_payload_bytes: int | None = None,
) -> FastAPI:
    """Build the FastAPI app with the supplied services.

    The factory is the seam tests use to inject fresh in-memory state
    per test case. ``uvicorn`` calls the same factory at runtime.

    The CRIT-1 fix changed the session transport from a bearer token in
    the JSON body to an HttpOnly+Secure+SameSite=strict cookie. The
    cookie name and the ``Secure`` flag are configurable so tests can
    exercise the contract under HTTP (the test client bypasses the
    ``Secure`` check anyway, but the flag still affects the header).

    PR-C.2 (R4 crit#3): when ``sweep_graph`` is supplied, the factory
    mounts a FastAPI ``lifespan`` that runs the call on a fixed
    interval (default 60s) and cancels the background task on
    shutdown. The default ``default_workbench_app`` factory does NOT
    pass ``sweep_graph`` because the dev server has no compiled graph
    to sweep; production deployments wire the real
    :func:`dafi_sentinel.orchestration.production_graph.production_graph`
    factory and pass the bound method here.
    """

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        """Start the paused-graph sweeper on startup; cancel it on shutdown.

        The lifespan is a no-op when ``sweep_graph`` is not supplied
        (e.g., the dev factory or any test that does not exercise the
        background sweeper). When it IS supplied, the lifespan creates
        a long-running task that calls the callable at
        ``sweeper_interval_seconds`` intervals; the task is cancelled
        on shutdown so a graceful uvicorn reload does not leak threads.
        """
        if sweep_graph is None:
            yield
            return

        import logging
        logger = logging.getLogger(__name__)

        stop = asyncio.Event()
        task: asyncio.Task[None] | None = None

        async def _run_sweeper() -> None:
            try:
                while not stop.is_set():
                    try:
                        sweep_graph()
                    except Exception:  # noqa: BLE001 — keep the task alive
                        logger.exception("paused-graph sweeper raised; continuing")
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=sweeper_interval_seconds)
                    except asyncio.TimeoutError:
                        continue
            except asyncio.CancelledError:
                # Explicit cancel from shutdown: surface for clean teardown.
                raise

        task = asyncio.create_task(_run_sweeper(), name="dafi-sweeper")
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    app = FastAPI(
        title="DAFI Sentinel Workbench API",
        version="0.5.0",
        description=(
            "PR5 owns the FastAPI auth/session surface and the "
            "evidence/QA/chart/role/audit endpoints. LangGraph and any "
            "third-party orchestration ship in PR6."
        ),
        lifespan=_lifespan,
    )

    # PR-C.3 (R1 high#4): install the production-readiness middleware
    # stack when the operator opts in. The middleware is OFF by default
    # so the dev factory and the existing test suite keep working
    # without changes; production deployments flip the flag (or set
    # ``DAFI_PRODUCTION_POSTURE=1`` and use the canonical production
    # factory the README documents).
    if enable_security_middleware:
        # HTTPSRedirect first: every request MUST arrive over TLS in
        # production. TestClient runs over plain HTTP, so the redirect
        # middleware will not fire in unit tests; the production
        # uvicorn / gunicorn fronting the app must terminate TLS.
        app.add_middleware(HTTPSRedirectMiddleware)
        # TrustedHost next: reject requests whose ``Host`` header is
        # not in the allow-list. The default is conservative
        # (``localhost`` + ``127.0.0.1``) so a forgotten config does
        # not silently open the surface.
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=list(security_allowed_hosts) or ["*"],
        )
        # CORS last so preflights consult the allow-list. Empty
        # allow-list means "no cross-origin requests", which is the
        # correct default for a server-to-server workbench API.
        if security_cors_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=list(security_cors_origins),
                allow_credentials=True,
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type"],
            )
        # HSTS via a tiny custom middleware so the response header
        # survives even when uvicorn terminates TLS upstream. The same
        # middleware also pins ``Cache-Control: no-store`` on the
        # sensitive endpoints (PR-C.7, R1 high#4) so a browser (or an
        # intermediate proxy) cannot keep the response on disk.
        @app.middleware("http")
        async def _hsts_middleware(request: Request, call_next: Callable[[Request], Any]) -> Any:
            response = await call_next(request)
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={hsts_max_age_seconds}; includeSubDomains",
            )
            if request.url.path.startswith("/sessions") or request.url.path == "/audits":
                response.headers["Cache-Control"] = "no-store"
            return response

    # PR-C.4 (R1 high#3): rate limits and payload-size caps on the
    # public mutation endpoints (``/sessions``, ``/qa``, ``/charts``).
    # Both layers are off by default so the dev factory and the
    # pre-PR-C.4 test suite keep working without changes. The limits
    # are in-process and per-key: a multi-worker deploy shares the
    # limits across workers only when the operator fronts the app
    # with a sticky-session proxy.
    if rate_limit_per_minute is not None or max_payload_bytes is not None:
        # Sliding window of request timestamps per key. The deque is
        # bounded by the rate limit so memory stays small. The
        # defaultdict is intentionally module-level (not on app.state)
        # so the rate limit survives a single process lifetime and
        # the lock contention stays inside one worker.
        _rate_log: dict[str, deque[float]] = defaultdict(deque)
        _rate_lock = asyncio.Lock()

        @app.middleware("http")
        async def _rate_limit_middleware(request: Request, call_next: Callable[[Request], Any]) -> Any:
            path = request.url.path
            if rate_limit_per_minute is not None and path in {"/sessions", "/qa", "/charts"} and request.method in {"POST"}:
                # /sessions is unauthenticated; rate-limit by client IP.
                # /qa and /charts are authenticated; we still rate-limit
                # by IP because the auth check happens downstream and
                # we want to shed load before doing the lookup.
                client_host = request.client.host if request.client else "unknown"
                key = f"{path}:{client_host}"
                now = monotonic()
                async with _rate_lock:
                    window = _rate_log[key]
                    cutoff = now - 60.0
                    while window and window[0] < cutoff:
                        window.popleft()
                    if len(window) >= rate_limit_per_minute:
                        return JSONResponse(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            content={"detail": "rate limit exceeded"},
                            headers={"Retry-After": "60"},
                        )
                    window.append(now)
            if max_payload_bytes is not None and request.method in {"POST", "PUT", "PATCH"}:
                content_length = request.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > max_payload_bytes:
                            return JSONResponse(
                                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                content={"detail": f"payload exceeds {max_payload_bytes} bytes"},
                            )
                    except ValueError:
                        pass
            return await call_next(request)

    app.state.auth = auth
    app.state.workbench = workbench
    app.state.gate = gate
    app.state.cookie_name = cookie_name
    app.state.cookie_secure = cookie_secure
    app.state.sweep_graph = sweep_graph

    def _resolve_token(request: Request) -> str:
        """Resolve a session token from the cookie first, then the bearer header.

        The cookie is the primary transport (dashboard path). The
        bearer header is a fallback kept for non-browser clients
        (curl, CLI). The dispatcher's CRIT-1 fix pins this two-path
        contract.
        """
        cookie_token = request.cookies.get(cookie_name)
        if cookie_token:
            return cookie_token
        return _extract_bearer(request)

    def _session_from_header(request: Request) -> tuple[Session, StoredUser]:
        token = _resolve_token(request)
        resolved = auth.resolve_session(token)
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired session")
        session, stored = resolved
        return session, stored

    def _current_user(request: Request) -> UserRef:
        _, stored = _session_from_header(request)
        return stored.user

    def _current_session(request: Request) -> Session:
        session, _ = _session_from_header(request)
        return session

    # ------------------------------------------------------------------ #
    # Sessions
    # ------------------------------------------------------------------ #

    @app.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
    def login(
        payload: LoginRequest, request: Request, response: Response
    ) -> SessionResponse:
        try:
            session = auth.login(payload.username, payload.password)
        except InvalidCredentialsError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        stored = auth.users.find_by_id(session.user_id)
        assert stored is not None  # login guarantees a stored user
        # R3 F18: hash the session token so the audit log carries an
        # opaque handle instead of the first 8 characters of the raw
        # token. The HttpOnly cookie transport stays the source of
        # truth for the live session; the audit log only needs a
        # stable correlation id.
        workbench.record_login(
            actor_id=stored.user.id,
            session_id=hash_session_id(session.token),
        )
        # CRIT-1: the session token lives in an HttpOnly+Secure+SameSite=strict
        # cookie. The JSON body MUST NOT carry the token so an XSS payload
        # cannot exfiltrate it. The cookie is the only transport the
        # browser will accept for subsequent dashboard requests.
        response.set_cookie(
            key=cookie_name,
            value=session.token,
            httponly=True,
            secure=cookie_secure,
            samesite="strict",
            path="/",
        )
        return SessionResponse(
            user_id=stored.user.id,
            display_name=stored.user.display_name,
            roles=tuple(role.name for role in stored.user.roles),
        )

    @app.delete("/sessions/me", status_code=status.HTTP_204_NO_CONTENT)
    def logout_via_cookie(request: Request) -> Response:
        """Logout the current session identified by the cookie.

        The dashboard calls this endpoint; the cookie carries the
        session token so the user can sign out without exposing the
        token in a URL path. The cookie is cleared in the response so
        the browser drops it.
        """
        token = _resolve_token(request)
        resolved = auth.resolve_session(token)
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        session, stored = resolved
        auth.logout(token)
        workbench.record_logout(
            actor_id=stored.user.id,
            session_id=hash_session_id(session.token),
        )
        # Build a 204 response that clears the session cookie. The
        # Secure flag must match the original ``Set-Cookie`` for the
        # browser to recognise this as the same cookie.
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(
            key=cookie_name,
            path="/",
            secure=cookie_secure,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.delete("/sessions/{token}", status_code=status.HTTP_204_NO_CONTENT)
    def logout(token: str, request: Request) -> None:
        """Logout via the bearer path (non-browser clients).

        The dashboard uses ``DELETE /sessions/me`` (cookie path). curl
        and CLI scripts can keep using this path with an
        ``Authorization: Bearer <token>`` header. The bearer and the
        path token MUST agree to prevent a user from revoking another
        user's session.

        R4 high#7: this path is deprecated and will be removed in a
        future release. The dashboard has migrated to
        ``DELETE /sessions/me`` (cookie transport); non-browser
        clients should switch to ``POST /sessions`` for re-auth or
        ``DELETE /sessions/me`` with a bearer-only flow. The
        ``Deprecation`` and ``Sunset`` response headers are set so
        clients can detect the scheduled removal.
        """
        resolved = auth.resolve_session(token)
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        session, stored = resolved
        bearer = _extract_bearer(request)
        if bearer != token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cannot revoke another user's session")
        auth.logout(token)
        workbench.record_logout(
            actor_id=stored.user.id,
            session_id=hash_session_id(session.token),
        )
        return None

    @app.get("/sessions/me", response_model=SessionResponse)
    def me(request: Request) -> SessionResponse:
        session, stored = _session_from_header(request)
        return SessionResponse(
            user_id=stored.user.id,
            display_name=stored.user.display_name,
            roles=tuple(role.name for role in stored.user.roles),
        )

    # ------------------------------------------------------------------ #
    # Evidence
    # ------------------------------------------------------------------ #

    @app.get("/evidence", response_model=list[EvidenceResponse])
    def list_evidence(request: Request) -> list[EvidenceResponse]:
        user = _current_user(request)
        records = workbench.list_owned_evidence(user.id)
        return [_evidence_to_response(record) for record in records]

    @app.get("/evidence/{evidence_id}", response_model=EvidenceResponse)
    def get_evidence(evidence_id: str, request: Request) -> EvidenceResponse:
        user = _current_user(request)
        try:
            record = workbench.get_evidence(user.id, evidence_id)
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return _evidence_to_response(record)

    # ------------------------------------------------------------------ #
    # Q&A
    # ------------------------------------------------------------------ #

    @app.post("/qa", response_model=QAResponse)
    def qa(payload: QuestionRequest, request: Request) -> QAResponse:
        user = _current_user(request)
        answer, cited = workbench.answer_question(
            actor_id=user.id,
            owner_id=user.id,
            session_id=payload.session_id,
            question=payload.question,
            limit=payload.limit,
        )
        cited_response = tuple(
            CitedEvidence(
                evidence_id=item.ref.evidence_id,
                source_uri=item.ref.source.uri,
                score=item.score,
            )
            for item in cited
        )
        return QAResponse(answer=answer, cited_evidence=cited_response, session_id=payload.session_id)

    # ------------------------------------------------------------------ #
    # Charts
    # ------------------------------------------------------------------ #

    @app.post("/charts", response_model=ChartResponse)
    def charts(payload: ChartRequest, request: Request) -> ChartResponse:
        user = _current_user(request)
        spec = _payload_to_spec(payload.spec)
        png_bytes = workbench.render_chart(
            actor_id=user.id,
            owner_id=user.id,
            spec=spec,
            data=payload.data,
        )
        cited = tuple(
            CitedEvidence(evidence_id=eid, source_uri="", score=0.0) for eid in spec.evidence_ids
        )
        return ChartResponse(
            spec=payload.spec,
            png_base64=png_to_base64(png_bytes),
            cited_evidence=cited,
        )

    # ------------------------------------------------------------------ #
    # Roles
    # ------------------------------------------------------------------ #

    @app.get("/roles/{user_id}", response_model=RoleResponse)
    def get_roles(user_id: str, request: Request) -> RoleResponse:
        actor = _current_user(request)
        stored = auth.users.find_by_id(user_id)
        if stored is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        try:
            require_owner(actor, user_id)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return RoleResponse(
            user_id=stored.user.id,
            display_name=stored.user.display_name,
            roles=tuple(role.name for role in stored.user.roles),
            permissions=tuple(
                permission.name for role in stored.user.roles for permission in role.permissions
            ),
        )

    # ------------------------------------------------------------------ #
    # Audits
    # ------------------------------------------------------------------ #

    @app.get("/audits", response_model=AuditsResponse)
    def list_audits(request: Request) -> AuditsResponse:
        actor = _current_user(request)
        records = workbench.list_audits(actor.id)
        return AuditsResponse(
            audits=tuple(
                AuditEntryResponse(
                    id=record.id,
                    actor_id=record.actor.id,
                    action=record.action,
                    allowed=record.decision.allowed,
                    reason=record.decision.reason,
                    timestamp=record.timestamp.isoformat(),
                    role_context=record.role_context,
                )
                for record in records
            )
        )

    @app.exception_handler(HTTPException)
    def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(ChartValidationError)
    def _chart_validation_handler(_: Request, exc: ChartValidationError) -> JSONResponse:
        """Map chart-spec validation failures to a structured 422 response.

        R3 F3: the 4R review caught that ``ChartValidationError`` was
        bubbling up as a generic 500 because FastAPI only knows how to
        map ``HTTPException``. The Pydantic ``ChartSpecPayload`` schema
        rejects an empty ``title`` (and any literal that violates the
        field constraints) before the request reaches the handler, but
        the domain validator is the source of truth for
        ``evidence_ids`` and the ``x`` / ``y`` axis fields. Mapping the
        exception to a 422 with ``{"detail": {"field": ..., "reason": ...}}``
        lets the dashboard render a useful inline error instead of an
        opaque failure.
        """
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": {"field": exc.field, "reason": exc.reason}},
        )

    return app


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return token


def _evidence_to_response(record: Any) -> EvidenceResponse:
    return EvidenceResponse(
        evidence_id=record.evidence_ref.evidence_id,
        source_uri=record.source.uri,
        source_row=record.source.row,
        source_offset=record.source.offset,
        redacted_summary=record.redacted_summary,
        timestamp=record.timestamp.isoformat() if isinstance(record.timestamp, datetime) else str(record.timestamp),
        fields=dict(record.fields),
    )


def _payload_to_spec(payload: ChartSpecPayload) -> ChartSpec:
    return ChartSpec(
        kind=payload.kind,
        title=payload.title,
        x=payload.x,
        y=payload.y,
        evidence_ids=payload.evidence_ids,
    )


def _dev_password(env_var: str = "DAFI_DEV_PASSWORD", *, length: int = 16) -> str:
    """Return a dev-only password for the seeded users.

    R1 high#1: the previous factory hardcoded ``"hunter2!"`` and a
    matching ``"correct horse"`` so anyone reading the repo could
    log in. The dev-only posture replaces both with a fresh token
    generated on every boot; the ``DAFI_DEV_PASSWORD`` env var
    overrides the random generation with a stable value so scripts
    and CI can pin a credential without checking the plaintext into
    source control. The function is local to the dev factory — it is
    never imported by production code.
    """
    import logging
    import os
    import secrets

    logger = logging.getLogger(__name__)
    override = os.environ.get(env_var)
    if override:
        return override
    generated = secrets.token_urlsafe(length)
    logger.warning(
        "DAFI_DEV_PASSWORD is not set; generated a random dev-only "
        "password for the seeded users: %s. Set DAFI_DEV_PASSWORD to "
        "pin a stable credential in local development.",
        generated,
    )
    return generated


def default_workbench_app() -> FastAPI:
    """Convenience factory wired with fresh in-memory services.

    Used by ``uvicorn dafi_sentinel.api.app:default_workbench_app`` in
    local development. Tests build their own app via
    :func:`create_workbench_app`.

    R4 crit#1: this factory is **dev-only**. The seeded users carry a
    random on-boot password (or a ``DAFI_DEV_PASSWORD`` override); the
    factory disables ``cookie_secure`` (browsers reject Secure cookies
    over the HTTP dev server) and gates the dashboard dev server CSP via
    the ``DAFI_DEV_NO_CSP_META=1`` env var so Vite HMR inline scripts
    are not blocked. Production deployments must:

    * Build the app via :func:`create_workbench_app` with
      ``cookie_secure=True`` and a real ``AuthService`` backed by a
      durable user store.
    * Set the ``DAFI_PRODUCTION_POSTURE`` env var so the application
      fails fast if the dev factory is reached in production.
    * Keep the strict meta-CSP — see :func:`create_workbench_app` for
      the production defaults.
    """
    import os

    from dafi_sentinel.api.auth import AuthService, InMemorySessionStore, InMemoryUserStore
    from dafi_sentinel.domain.models import Permission, Role
    from dafi_sentinel.retrieval.contracts import InMemoryRetrievalIndex

    if os.environ.get("DAFI_PRODUCTION_POSTURE") == "1":
        raise RuntimeError(
            "default_workbench_app is dev-only; production must call "
            "create_workbench_app with a real user store and "
            "cookie_secure=True."
        )

    dev_password = _dev_password()
    users = InMemoryUserStore()
    users.add(
        "user-1",
        "Analyst",
        "ada",
        dev_password,
        roles=(Role("analyst", permissions=(Permission("chart:request"),)),),
    )
    users.add(
        "user-2",
        "Maintainer",
        "mike",
        dev_password,
        roles=(Role("maintainer", permissions=(Permission("tool:python"),)),),
    )

    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
        retrieval_index=InMemoryRetrievalIndex(()),
    )
    return create_workbench_app(
        auth=AuthService(users=users, sessions=InMemorySessionStore()),
        workbench=workbench,
        cookie_secure=False,
    )


__all__ = ["create_workbench_app", "default_workbench_app"]
