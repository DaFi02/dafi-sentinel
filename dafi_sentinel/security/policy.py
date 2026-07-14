from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import re

from dafi_sentinel.domain.models import ActorRef, AuditRecord, Permission, PolicyDecision, UserRef


SECRET_PATTERN = re.compile(r"(?P<token>sk_(?:live|test)_[A-Za-z0-9]+)|password=(?P<password>[^\s]+)", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class Approval:
    approved: bool
    approver_id: str


@dataclass
class AuditSink:
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    records: list[AuditRecord] = field(default_factory=list)

    def record(self, session_id: str, actor: ActorRef, action: str, decision: PolicyDecision, roles: tuple[str, ...]) -> None:
        self.records.append(
            AuditRecord(
                id=f"audit-{session_id}-{len(self.records) + 1}",
                actor=actor,
                action=action,
                decision=decision,
                timestamp=self.clock(),
                role_context=roles,
            )
        )


@dataclass
class RedactionService:
    _markers: dict[tuple[str, str], str] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)

    def redact_text(self, value: str) -> str:
        redacted = SECRET_PATTERN.sub(self._redact_secret_match, value)
        return EMAIL_PATTERN.sub(lambda match: self._marker("PII", match.group(0)), redacted)

    def redact_value(self, value: object) -> object:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {key: self.redact_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        return value

    def _marker(self, category: str, raw: str) -> str:
        key = (category, raw)
        if key not in self._markers:
            self._counts[category] = self._counts.get(category, 0) + 1
            self._markers[key] = f"[REDACTED:{category}:{self._counts[category]}]"
        return self._markers[key]

    def _redact_secret_match(self, match: re.Match[str]) -> str:
        if match.group("password") is not None:
            return f"password={self._marker('SECRET', match.group('password'))}"
        return self._marker("SECRET", match.group(0))


@dataclass
class SecurityGate:
    redactor: RedactionService
    audits: AuditSink
    disclosure_policy: str = "redacted-only"

    def inspect_evidence(self, actor: ActorRef, session_id: str, text: str) -> PolicyDecision:
        self.redactor.redact_text(text)
        decision = PolicyDecision(True, "incident content treated as untrusted data")
        self.audits.record(session_id, actor, "evidence.inspect", decision, ())
        return decision

    def inspect_user_request(self, actor: ActorRef, session_id: str, text: str) -> PolicyDecision:
        normalized = text.lower()
        if "unredacted" in normalized or "secret" in normalized:
            decision = PolicyDecision(False, "redacted-only disclosure boundary", Permission("secrets:reveal"))
            self.audits.record(session_id, actor, "request.inspect", decision, ())
            return decision

        decision = PolicyDecision(True, "request allowed")
        self.audits.record(session_id, actor, "request.inspect", decision, ())
        return decision

    def authorize_tool(
        self,
        actor: ActorRef,
        user: UserRef,
        tool_name: str,
        session_id: str,
        approval: Approval | None = None,
    ) -> PolicyDecision:
        permission = Permission(f"tool:{tool_name}")
        roles = tuple(role.name for role in user.roles)

        if not any(role.allows(permission.name) for role in user.roles):
            decision = PolicyDecision(False, f"missing permission {permission.name}", permission)
        elif tool_name == "python" and approval is None:
            decision = PolicyDecision(False, "approval required for controlled python execution", permission)
        elif tool_name == "python" and approval is not None and not approval.approved:
            decision = PolicyDecision(False, f"approval denied by {approval.approver_id}", permission)
        elif tool_name == "python" and approval is not None:
            decision = PolicyDecision(True, f"approved by {approval.approver_id}", permission)
        else:
            decision = PolicyDecision(True, "permission allowed", permission)

        self.audits.record(session_id, actor, f"tool.{tool_name}", decision, roles)
        return decision
