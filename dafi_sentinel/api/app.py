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

from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from dafi_sentinel.api.auth import (
    AuthService,
    InvalidCredentialsError,
    Session,
    StoredUser,
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
from dafi_sentinel.api.services import (
    InMemoryAuditRepository,
    InMemoryEvidenceRepository,
    WorkbenchService,
    png_to_base64,
)
from dafi_sentinel.domain.models import ActorRef, ChartSpec, UserRef


def create_workbench_app(
    *,
    auth: AuthService,
    workbench: WorkbenchService,
) -> FastAPI:
    """Build the FastAPI app with the supplied services.

    The factory is the seam tests use to inject fresh in-memory state
    per test case. ``uvicorn`` calls the same factory at runtime.
    """

    app = FastAPI(
        title="DAFI Sentinel Workbench API",
        version="0.5.0",
        description=(
            "PR5 owns the FastAPI auth/session surface and the "
            "evidence/QA/chart/role/audit endpoints. LangGraph and any "
            "third-party orchestration ship in PR6."
        ),
    )
    app.state.auth = auth
    app.state.workbench = workbench

    def _session_from_header(request: Request) -> tuple[Session, StoredUser]:
        token = _extract_bearer(request)
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
    def login(payload: LoginRequest, request: Request) -> SessionResponse:
        try:
            session = auth.login(payload.username, payload.password)
        except InvalidCredentialsError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        stored = auth.users.find_by_id(session.user_id)
        assert stored is not None  # login guarantees a stored user
        workbench.record_login(actor_id=stored.user.id, session_id=session.token[:8])
        return SessionResponse(
            token=session.token,
            user_id=stored.user.id,
            display_name=stored.user.display_name,
            roles=tuple(role.name for role in stored.user.roles),
        )

    @app.delete("/sessions/{token}", status_code=status.HTTP_204_NO_CONTENT)
    def logout(token: str, request: Request) -> None:
        resolved = auth.resolve_session(token)
        if resolved is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        session, stored = resolved
        # The bearer header and the path token must agree, otherwise a
        # logged-in user could log out a different user's session.
        bearer = _extract_bearer(request)
        if bearer != token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cannot revoke another user's session")
        auth.logout(token)
        workbench.record_logout(actor_id=stored.user.id, session_id=session.token[:8])
        return None

    @app.get("/sessions/me", response_model=SessionResponse)
    def me(request: Request) -> SessionResponse:
        session, stored = _session_from_header(request)
        return SessionResponse(
            token=session.token,
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
                evidence_id=ref.evidence_id,
                source_uri=ref.source.uri,
                score=0.0,
            )
            for ref in cited
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
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

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


def default_workbench_app() -> FastAPI:
    """Convenience factory wired with fresh in-memory services.

    Used by ``uvicorn dafi_sentinel.api.app:default_workbench_app`` in
    local development. Tests build their own app via
    :func:`create_workbench_app`.
    """
    from dafi_sentinel.api.auth import AuthService, InMemorySessionStore, InMemoryUserStore
    from dafi_sentinel.domain.models import Permission, Role

    users = InMemoryUserStore()
    users.add(
        "user-1",
        "Analyst",
        "ada",
        "hunter2!",
        roles=(Role("analyst", permissions=(Permission("chart:request"),)),),
    )

    workbench = WorkbenchService(
        evidence=InMemoryEvidenceRepository(),
        audits=InMemoryAuditRepository(),
    )
    return create_workbench_app(
        auth=AuthService(users=users, sessions=InMemorySessionStore()),
        workbench=workbench,
    )


__all__ = ["create_workbench_app", "default_workbench_app"]
