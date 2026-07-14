from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import re

from dafi_sentinel.domain.models import ActorRef, AuditRecord, Permission, PolicyDecision, UserRef


# PR-C.13 (R1 med#11): widen the redaction regex to cover the
# common secret shapes the 4R review flagged. The pattern keeps
# the same named-group shape as the pre-PR-C.13 surface so the
# ``_redact_secret_match`` helper can keep the "key=value" prefix
# when one is present. The order of the alternation matters: the
# longest match wins, so ``api_key=sk_live_...`` is captured by
# the ``api_key`` group, not the ``token`` group.
SECRET_PATTERN = re.compile(
    r"(?:"
    r"(?P<token>sk_(?:live|test)_[A-Za-z0-9]+)"
    r"|password=(?P<password>[^\s]+)"
    r"|aws_access_key_id=(?P<aws_access_key>[A-Za-z0-9]+)"
    r"|aws_secret_access_key=(?P<aws_secret_key>[A-Za-z0-9/+=]+)"
    r"|(?P<github_pat>github_pat_[A-Za-z0-9_]+)"
    r"|(?P<github_classic>gh[ps]_[A-Za-z0-9]+)"
    r"|(?P<jwt>eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"
    r"|api_key=(?P<api_key>[^\s]+)"
    r")",
    re.IGNORECASE,
)
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
        # The named groups for key=value shapes carry ONLY the value
        # (the prefix lives outside the group), so the redaction
        # helper rebuilds the "key=[REDACTED:SECRET:N]" string. The
        # "bare token" patterns (sk_live_, github_pat_, JWT) capture
        # the entire secret in the group, so the fallback uses
        # ``match.group(0)``.
        if match.group("password") is not None:
            return f"password={self._marker('SECRET', match.group('password'))}"
        if match.group("api_key") is not None:
            return f"api_key={self._marker('SECRET', match.group('api_key'))}"
        if match.group("aws_access_key") is not None:
            return f"aws_access_key_id={self._marker('SECRET', match.group('aws_access_key'))}"
        if match.group("aws_secret_key") is not None:
            return f"aws_secret_access_key={self._marker('SECRET', match.group('aws_secret_key'))}"
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
