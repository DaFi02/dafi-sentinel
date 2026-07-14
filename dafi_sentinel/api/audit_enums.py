"""Strongly-typed audit action and reason constants (R2 high#3).

The 4R review caught that audit actions and reasons were free-form
strings sprinkled across :mod:`dafi_sentinel.api.services`,
:mod:`dafi_sentinel.orchestration.graph`, and
:mod:`dafi_sentinel.api.app`. A typo in any of those call sites
silently produced a new audit action (or reason) and the test suite
would never notice. The fix lifts the canonical action and reason
strings into enums so:

* The set of legal actions is enumerated in one place.
* ``mypy`` flags a stray literal that does not match the enum.
* The ``AuditRecord.action`` field stays a string (the wire format is
  unchanged) so the on-disk audit log and the existing
  ``/audits`` payload format are unaffected.

The enum members use the ``str`` mixin so they round-trip through the
``AuditRecord.action`` column without explicit ``.value`` access.
"""

from __future__ import annotations

from enum import Enum


class AuditAction(str, Enum):
    """Canonical audit actions emitted by the workbench services.

    The enum value matches the wire format that the existing audit
    store and ``/audits`` payload expect. New actions must be added
    here so a typo is impossible at any call site.
    """

    QA_ANSWER = "qa.answer"
    CHART_RENDER = "chart.render"
    SESSION_LOGIN = "session.login"
    SESSION_LOGOUT = "session.logout"
    ORCHESTRATION_INSPECT = "orchestration.inspect"
    ORCHESTRATION_RETRIEVE = "orchestration.retrieve"
    ORCHESTRATION_APPROVAL = "orchestration.approval"
    ORCHESTRATION_RENDER_CHART = "orchestration.render_chart"
    ORCHESTRATION_FINALIZE = "orchestration.finalize"


class AuditReason(str, Enum):
    """Canonical static audit reasons emitted by the workbench services.

    Dynamic reasons (e.g., ``f"chart {kind} rendered with {n} evidence
    ids"``) keep building the string at the call site because their
    template depends on the request; the static ones (refusal, login
    success, etc.) are enumerated here so a reviewer can grep a single
    file for the legal outcomes.
    """

    LOGIN_SUCCEEDED = "login succeeded"
    LOGOUT_SUCCEEDED = "logout succeeded"
    EVIDENCE_CITED = "evidence cited"
    NO_SUPPORTING_EVIDENCE = "no supporting evidence"
    NO_SUPPORTING_EVIDENCE_DASH = "no-supporting-evidence"
    APPROVAL_AUTHORIZED = "approval-authorized"
    APPROVAL_DENIED = "approval-denied"
    APPROVAL_SELF_OR_UNAUTHORIZED = "approval-self-or-unauthorized"
    APPROVAL_TIMEOUT = "approval-timeout"
    REQUEST_ALLOWED = "request allowed"
    REDACTED_ONLY_DISCLOSURE = "redacted-only disclosure boundary"
    UNTRUSTED_DATA = "incident content treated as untrusted data"
