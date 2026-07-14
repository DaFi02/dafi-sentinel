"""Pydantic request/response schemas for the PR5 workbench API.

The schemas intentionally mirror the domain dataclasses so the workbench
service can translate between FastAPI's contract and the existing
``dafi_sentinel.domain.models`` types without leaking pydantic
dependencies into the domain layer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # PR-C.5 (R1 high#5): cap the password so a malicious caller
    # cannot pin a 10 MB string and exhaust the argon2 verifier (the
    # 4R review caught that the prior field had no upper bound). The
    # 256-char ceiling is well above any sane password and well below
    # the size at which argon2's KDF cost becomes an obvious DoS.
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class SessionResponse(BaseModel):
    """User profile returned by /sessions and /sessions/me.

    The CRIT-1 fix removes the bearer token from the response body. The
    token lives in an HttpOnly cookie set on the login response; the
    body only carries the user profile fields the dashboard needs to
    render the authenticated shell.
    """

    user_id: str
    display_name: str
    roles: tuple[str, ...] = ()


class EvidenceResponse(BaseModel):
    evidence_id: str
    source_uri: str
    source_row: int | None
    source_offset: int | None
    redacted_summary: str
    timestamp: str
    fields: dict[str, Any] = Field(default_factory=dict)


class QuestionRequest(BaseModel):
    # PR-C.5 (R1 high#5): cap the question body so a 100 KB text blob
    # cannot reach the retrieval pipeline. 2048 chars is well above
    # the longest real question the dashboard renders and is the
    # sweet spot the 4R review flagged as the production ceiling.
    question: str = Field(min_length=1, max_length=2048)
    session_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=5, ge=1, le=50)


class CitedEvidence(BaseModel):
    evidence_id: str
    source_uri: str
    score: float


class QAResponse(BaseModel):
    answer: str
    cited_evidence: tuple[CitedEvidence, ...] = ()
    session_id: str


class ChartRequest(BaseModel):
    spec: "ChartSpecPayload"
    data: tuple[tuple[Any, Any], ...] = ()


class ChartSpecPayload(BaseModel):
    kind: Literal["line", "bar", "scatter", "table"]
    title: str = Field(min_length=1)
    x: str = ""
    y: str = ""
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)


class ChartResponse(BaseModel):
    spec: ChartSpecPayload
    png_base64: str
    cited_evidence: tuple[CitedEvidence, ...] = ()


class RoleResponse(BaseModel):
    user_id: str
    display_name: str
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()


class AuditEntryResponse(BaseModel):
    id: str
    actor_id: str
    action: str
    allowed: bool
    reason: str
    timestamp: str
    role_context: tuple[str, ...] = ()


class AuditsResponse(BaseModel):
    audits: tuple[AuditEntryResponse, ...] = ()


class ErrorResponse(BaseModel):
    detail: str


ChartRequest.model_rebuild()
