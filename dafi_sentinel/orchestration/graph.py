"""Investigation state machine for the PR6 workbench.

The graph composes the existing deterministic services:

* PR1 — :mod:`dafi_sentinel.domain.models` contracts and the
  :class:`AuditRepository` protocol.
* PR2 — :class:`SecurityGate` for prompt-boundary inspection and the
  redaction service.
* PR3 — :class:`InMemoryRetrievalIndex` (or any ``RetrievalIndex``
  implementation) via :class:`WorkbenchService.answer_question`.
* PR4 — :class:`WorkbenchService.render_chart` (which composes
  :mod:`dafi_sentinel.ml.analysis` and :mod:`dafi_sentinel.charts`).
* PR5 — :class:`WorkbenchService` orchestration surface.

The graph itself adds two capabilities:

1. An explicit approval pause before the controlled action (chart
   render) using :func:`langgraph.types.interrupt`. The pause propagates
   the in-progress state through the :class:`InMemorySaver` checkpointer
   so a separate approval step (test helper or CLI) can resume it.
2. A finalize node that always writes a :class:`PolicyDecision` audit
   record. When the approval is denied, the decision is
   ``allowed=False, reason="approval-denied"``; when no evidence
   supports the question, the decision is
   ``allowed=False, reason="no-supporting-evidence"``; when the chart
   is approved, the decision carries the approver id.

The graph NEVER reimplements retrieval, ranking, redaction, or chart
rendering. It only wires those services together.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from operator import add
from typing import Annotated, Any, Literal, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from dafi_sentinel.api.audit_enums import AuditAction, AuditReason
from dafi_sentinel.api.services import WorkbenchService, new_audit_id
from dafi_sentinel.domain.models import ActorRef, AuditRecord, Permission, PolicyDecision, Role, UserRef
from dafi_sentinel.security.policy import SecurityGate
from dafi_sentinel.storage.contracts import AuditRepository


# --------------------------------------------------------------------------- #
# Module-level guard
# --------------------------------------------------------------------------- #

import logging

logger = logging.getLogger(__name__)
# The default InMemorySaver is process-local; production deployments MUST
# swap in a durable checkpointer (e.g., Postgres). Surfacing the warning
# at import time makes the requirement visible to operators.
logger.warning(
    "InMemorySaver is process-local; production must use a durable checkpointer (e.g., Postgres)."
)


# --------------------------------------------------------------------------- #
# Approver authorization
# --------------------------------------------------------------------------- #


APPROVER_PERMISSION = "approval:grant"
"""Permission required for a user to grant an approval.

The CRIT-2 fix enforces this permission on the approver (not just
separation of duties) so a low-privilege user cannot grant controlled
actions.
"""


# R3 F8: the system approver identity used by the CRIT-6 sweeper is
# declared before its first reference so the module reads top-down
# without a forward-declaration dance. The role carries the
# ``approval:grant`` permission so the authorization check passes
# when the sweeper resumes a paused graph.
_SYSTEM_APPROVER = UserRef(
    id="system",
    display_name="System",
    roles=(Role("system", permissions=(Permission(APPROVER_PERMISSION),)),),
)


# --------------------------------------------------------------------------- #
# Public state + payload contracts
# --------------------------------------------------------------------------- #


class InvestigationState(TypedDict, total=False):
    """State carried by the investigation graph.

    The TypedDict is ``total=False`` so each node can return a partial
    update. The ``audit_records`` field uses the ``add`` reducer so
    every node APPENDS its audit entries without clobbering prior
    nodes' entries.
    """

    # Inputs the caller sets on the initial invoke.
    actor_id: str
    actor_kind: str
    owner_id: str
    session_id: str
    question: str
    chart_kind: str
    chart_title: str
    chart_x: str
    chart_y: str
    chart_data: list[tuple[object, object]]
    chart_evidence_ids: list[str]

    # Populated by the inspect/retrieve/compose nodes.
    cited: list[str]
    answer: str

    # Populated by the request_approval + render_chart nodes.
    chart_png: bytes | None
    approval_granted: bool
    approval_approver: str

    # Populated by the finalize node.
    decision_reason: str

    # Audit accumulator — every stateful node appends one entry.
    audit_records: Annotated[list[dict[str, Any]], add]


@dataclass(frozen=True)
class ApprovalRequest:
    """Payload exchanged at the approval node.

    The approval node calls :func:`langgraph.types.interrupt` with this
    shape; a separate approval step (test helper or CLI) resumes the
    graph with an :class:`ApprovalRequest` instance.

    The CRIT-2 fix changed the resume value from a bare ``approver_id``
    to a full :class:`UserRef` so the graph can enforce separation of
    duties and the ``approval:grant`` permission without a side
    user-store lookup.
    """

    approved: bool
    approver: UserRef | None = None


# --------------------------------------------------------------------------- #
# Graph factory
# --------------------------------------------------------------------------- #


def build_investigation_graph(
    *,
    workbench: WorkbenchService,
    gate: SecurityGate,
    audits: AuditRepository,
    checkpointer: BaseCheckpointSaver | None = None,
    paused_graph_ttl_seconds: int = 3600,
    clock: Callable[[], datetime] | None = None,
) -> Any:
    """Compile and return the investigation state machine.

    The graph visits these nodes in order:

    1. ``inspect`` — security gate prompt-boundary inspection.
    2. ``retrieve`` — workbench Q&A (PR3 retrieval + PR4 ranker).
    3. ``compose_answer`` — fold the cited evidence into the answer.
    4. ``request_approval`` — :func:`langgraph.types.interrupt` for the
       chart-render approval.
    5. ``render_chart`` (conditional) — workbench chart render (PR4).
    6. ``finalize`` — always-run terminal node that records the
       :class:`PolicyDecision` audit.

    The default checkpointer is an :class:`InMemorySaver` so the graph
    can pause and resume in tests. Production deployments MUST swap
    in a durable checkpointer (e.g., Postgres); the module-level
    logger warning makes the requirement visible at import time.

    ``paused_graph_ttl_seconds`` is the orphan-handling TTL exposed
    by the CRIT-6 fix. Operators run :func:`sweep_stale_pauses` against
    the compiled graph with this TTL; stale paused threads are
    finalized with ``decision_reason='approval-timeout'`` so the
    audit trail captures abandoned investigations.

    The ``clock`` parameter (R3 F2) is the seam replay-based review
    relies on: every audit record produced by the inspection, retrieval,
    approval, render, and finalize nodes is timestamped with
    ``clock()`` instead of the wall clock. The default preserves the
    pre-fix behavior (``datetime.now(UTC)``) so existing callers do
    not need to change.
    """

    effective_clock = clock or (lambda: datetime.now(UTC))

    builder = StateGraph(InvestigationState)
    builder.add_node("inspect", _make_inspect_node(gate, audits, effective_clock))
    builder.add_node("retrieve", _make_retrieve_node(workbench, audits, effective_clock))
    builder.add_node("compose_answer", _make_compose_node())
    builder.add_node("request_approval", _make_approval_node(audits, effective_clock))
    builder.add_node("render_chart", _make_render_node(workbench, audits, effective_clock))
    builder.add_node("finalize", _make_finalize_node(audits, effective_clock))

    builder.add_edge(START, "inspect")
    builder.add_edge("inspect", "retrieve")
    builder.add_edge("retrieve", "compose_answer")
    builder.add_conditional_edges(
        "compose_answer",
        _route_after_compose,
        {"approval": "request_approval", "finalize": "finalize"},
    )
    builder.add_conditional_edges(
        "request_approval",
        _route_after_approval,
        {"render_chart": "render_chart", "finalize": "finalize"},
    )
    builder.add_edge("render_chart", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())


# --------------------------------------------------------------------------- #
# Routing helpers
# --------------------------------------------------------------------------- #


def _route_after_compose(state: InvestigationState) -> Literal["approval", "finalize"]:
    """Skip the approval step when there is nothing to render or approve."""
    if state.get("cited"):
        return "approval"
    return "finalize"


def _route_after_approval(state: InvestigationState) -> Literal["render_chart", "finalize"]:
    """Route to the chart render only when the approver granted consent."""
    if state.get("approval_granted"):
        return "render_chart"
    return "finalize"


# --------------------------------------------------------------------------- #
# Node factories — every factory returns a callable that mutates the state
# --------------------------------------------------------------------------- #


def _actor(state: InvestigationState) -> ActorRef:
    kind = state.get("actor_kind") or "user"
    actor_id = state.get("actor_id") or ""
    return ActorRef(id=actor_id, kind=cast(Any, kind))


def _make_inspect_node(
    gate: SecurityGate,
    audits: AuditRepository,
    clock: Callable[[], datetime],
) -> Callable[[InvestigationState], dict[str, Any]]:
    def inspect(state: InvestigationState) -> dict[str, Any]:
        actor = _actor(state)
        decision = gate.inspect_user_request(actor, state["session_id"], state["question"])

        record = _build_audit_record(
            actor=actor,
            action=AuditAction.ORCHESTRATION_INSPECT,
            decision=decision,
            session_id=state["session_id"],
            role_context=(state.get("owner_id") or "",),
            clock=clock,
        )
        audits.write_audit(state["session_id"], record)

        return {"audit_records": [_serialize_audit(record)]}

    return inspect


def _make_retrieve_node(
    workbench: WorkbenchService,
    audits: AuditRepository,
    clock: Callable[[], datetime],
) -> Callable[[InvestigationState], dict[str, Any]]:
    def retrieve(state: InvestigationState) -> dict[str, Any]:
        answer, cited = workbench.answer_question(
            actor_id=state["actor_id"],
            owner_id=state["owner_id"],
            session_id=state["session_id"],
            question=state["question"],
            limit=5,
        )

        actor = _actor(state)
        decision = PolicyDecision(
            allowed=bool(cited),
            reason=(AuditReason.EVIDENCE_CITED if cited else AuditReason.NO_SUPPORTING_EVIDENCE),
        )
        record = _build_audit_record(
            actor=actor,
            action=AuditAction.ORCHESTRATION_RETRIEVE,
            decision=decision,
            session_id=state["session_id"],
            role_context=(state.get("owner_id") or "",),
            clock=clock,
        )
        audits.write_audit(state["session_id"], record)

        return {
            "answer": answer,
            "cited": [item.ref.evidence_id for item in cited],
            "audit_records": [_serialize_audit(record)],
        }

    return retrieve


def _make_compose_node() -> Callable[[InvestigationState], dict[str, Any]]:
    def compose(state: InvestigationState) -> dict[str, Any]:
        # The retrieve node already composed the answer. Nothing to do
        # here; the node exists so the routing layer has a clean seam
        # between retrieval and the approval gate.
        return {}

    return compose


def _make_approval_node(
    audits: AuditRepository,
    clock: Callable[[], datetime],
) -> Callable[[InvestigationState], dict[str, Any]]:
    def request_approval(state: InvestigationState) -> dict[str, Any]:
        requestor_id = state.get("actor_id") or ""
        # Pause execution and surface the approval prompt to the caller.
        # The caller resumes the graph with ``Command(resume=ApprovalRequest(...))``.
        resume_value = interrupt(
            {
                "action": "render_chart",
                "evidence_ids": list(state.get("cited", ())),
                "session_id": state["session_id"],
            }
        )
        approval = _coerce_approval(resume_value)

        # R2 high#1: split the 4-return-path approval node into named
        # helpers so each branch is testable in isolation. The control
        # flow stays identical; the helpers just give names to what was
        # previously inlined.
        actor, decision = _check_authorization(
            requestor_id=requestor_id,
            approver=approval.approver,
            approved=approval.approved,
        )
        state_update = _record_approval_decision(
            audits=audits,
            clock=clock,
            state=state,
            actor=actor,
            approver=approval.approver,
            decision=decision,
        )
        return state_update

    return request_approval


def _check_authorization(
    *,
    requestor_id: str,
    approver: UserRef | None,
    approved: bool,
) -> tuple[ActorRef, PolicyDecision]:
    """Resolve the approver authorization decision for the approval node.

    Returns a ``(actor, decision)`` pair. The ``actor`` is who to
    attribute the audit record to (the requestor when the resume
    payload is malformed, the approver otherwise); the ``decision`` is
    the :class:`PolicyDecision` for that branch.

    The four possible outcomes are:

    1. No approver in the resume payload → unauthorized denial.
    2. Approver is the requestor (separation of duties) → unauthorized denial.
    3. Approver lacks the ``approval:grant`` permission → unauthorized denial.
    4. Sweeper-resumed system approver → timeout denial.
    5. Otherwise → either approval or refusal, attributed to the approver.
    """
    # 1. Missing approver (legacy / malformed resume payload).
    if approver is None:
        return (
            ActorRef(id=requestor_id, kind="user"),
            PolicyDecision(allowed=False, reason=AuditReason.APPROVAL_SELF_OR_UNAUTHORIZED),
        )

    # 2 + 3. Separation of duties and permission check.
    authz = _evaluate_approver(requestor_id=requestor_id, approver=approver)
    if not authz.allowed:
        return (
            ActorRef(id=approver.id, kind="user"),
            authz,
        )

    # 4. CRIT-6 sweeper path: the system approver carries the
    # ``approval:grant`` permission via its implicit role, so the authz
    # check above passes. Detect the system path and surface the
    # timeout reason so the audit trail captures the abandonment.
    if approver.id == _SYSTEM_APPROVER.id:
        return (
            ActorRef(id=approver.id, kind="user"),
            PolicyDecision(allowed=False, reason=AuditReason.APPROVAL_TIMEOUT),
        )

    # 5. Normal human approver: respect the approver's verdict.
    return (
        ActorRef(id=approver.id, kind="user"),
        PolicyDecision(
            allowed=approved,
            reason=(
                f"approved-by-{approver.id}" if approved
                else AuditReason.APPROVAL_DENIED
            ),
        ),
    )


def _record_approval_decision(
    *,
    audits: AuditRepository,
    clock: Callable[[], datetime],
    state: InvestigationState,
    actor: ActorRef,
    approver: UserRef | None,
    decision: PolicyDecision,
) -> dict[str, Any]:
    """Persist the approval audit record and return the state update.

    The audit record is attributed to the supplied ``actor``; the
    state update carries the ``approval_granted`` / ``approval_approver``
    / ``decision_reason`` fields the rest of the graph reads. The
    ``role_context`` falls back to the owner id when the approver is
    absent so the audit trail still surfaces the requestor.
    """
    role_context = (
        tuple(role.name for role in approver.roles) if approver is not None
        else (state.get("owner_id") or "",)
    )
    record = _build_audit_record(
        actor=actor,
        action=AuditAction.ORCHESTRATION_APPROVAL,
        decision=decision,
        session_id=state["session_id"],
        role_context=role_context,
        clock=clock,
    )
    audits.write_audit(state["session_id"], record)
    return {
        "approval_granted": decision.allowed,
        "approval_approver": approver.id if approver is not None else "",
        "decision_reason": decision.reason,
        "audit_records": [_serialize_audit(record)],
    }


def _make_render_node(
    workbench: WorkbenchService,
    audits: AuditRepository,
    clock: Callable[[], datetime],
) -> Callable[[InvestigationState], dict[str, Any]]:
    def render_chart(state: InvestigationState) -> dict[str, Any]:
        from dafi_sentinel.domain.models import ChartSpec

        actor = _actor(state)
        spec = ChartSpec(
            kind=cast(Any, state.get("chart_kind") or "bar"),
            title=state.get("chart_title") or "Investigation chart",
            x=state.get("chart_x") or "evidence_id",
            y=state.get("chart_y") or "value",
            evidence_ids=tuple(state.get("chart_evidence_ids") or state.get("cited") or ()),
        )
        data: list[tuple[object, object]] = list(state.get("chart_data") or ())

        try:
            png_bytes = workbench.render_chart(
                actor_id=state["actor_id"],
                owner_id=state["owner_id"],
                spec=spec,
                data=data,
            )
            decision = PolicyDecision(
                allowed=True,
                reason=f"chart {spec.kind} rendered with {len(spec.evidence_ids)} evidence ids",
            )
            record = _build_audit_record(
                actor=actor,
                action=AuditAction.ORCHESTRATION_RENDER_CHART,
                decision=decision,
                session_id=state["session_id"],
                role_context=(state.get("owner_id") or "",),
                clock=clock,
            )
            audits.write_audit(state["session_id"], record)
            return {
                "chart_png": png_bytes,
                "audit_records": [_serialize_audit(record)],
            }
        except (ValueError, LookupError) as exc:
            # Surface the failure as a denial-style audit so the
            # finalize node can still produce a PolicyDecision.
            decision = PolicyDecision(
                allowed=False,
                reason=f"chart render failed: {exc}",
            )
            record = _build_audit_record(
                actor=actor,
                action=AuditAction.ORCHESTRATION_RENDER_CHART,
                decision=decision,
                session_id=state["session_id"],
                role_context=(state.get("owner_id") or "",),
                clock=clock,
            )
            audits.write_audit(state["session_id"], record)
            return {
                "chart_png": None,
                "decision_reason": f"chart-render-failed: {exc}",
                "audit_records": [_serialize_audit(record)],
            }

    return render_chart


def _make_finalize_node(
    audits: AuditRepository,
    clock: Callable[[], datetime],
) -> Callable[[InvestigationState], dict[str, Any]]:
    def finalize(state: InvestigationState) -> dict[str, Any]:
        actor = _actor(state)
        existing_reason = state.get("decision_reason")
        approved = bool(state.get("approval_granted"))

        if existing_reason in {AuditReason.APPROVAL_DENIED, AuditReason.NO_SUPPORTING_EVIDENCE_DASH} or str(existing_reason or "").startswith("chart-render-failed"):
            decision_reason = existing_reason or AuditReason.APPROVAL_DENIED
            decision = PolicyDecision(allowed=False, reason=decision_reason)
        elif not state.get("cited"):
            decision_reason = AuditReason.NO_SUPPORTING_EVIDENCE_DASH
            decision = PolicyDecision(allowed=False, reason=decision_reason)
        elif approved:
            approver = state.get("approval_approver") or "unknown"
            decision_reason = f"approved-by-{approver}"
            decision = PolicyDecision(allowed=True, reason=decision_reason)
        else:
            decision_reason = existing_reason or AuditReason.APPROVAL_DENIED
            decision = PolicyDecision(allowed=False, reason=decision_reason)

        record = _build_audit_record(
            actor=actor,
            action=AuditAction.ORCHESTRATION_FINALIZE,
            decision=decision,
            session_id=state["session_id"],
            role_context=(state.get("owner_id") or "",),
            clock=clock,
        )
        audits.write_audit(state["session_id"], record)

        return {
            "decision_reason": decision_reason,
            "audit_records": [_serialize_audit(record)],
        }

    return finalize


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _coerce_approval(value: Any) -> ApprovalRequest:
    """Coerce the resume value (which round-trips through pickle) into an :class:`ApprovalRequest`.

    The approver MUST be a :class:`UserRef` (or a dict with the same
    shape). A missing or malformed approver resolves to ``approver=None``;
    the approval node then records the decision as
    ``approval-self-or-unauthorized`` and skips the chart render.

    R2 high#10 / R3 F19: the prior ``approver_id`` fallback accepted a
    bare string id (without roles) as an approver. The fallback was
    removed: a missing ``approver`` field now means a denial, and a
    caller wanting to attribute a decision to a specific human must
    supply a :class:`UserRef` with the ``approval:grant`` permission.
    """
    if isinstance(value, ApprovalRequest):
        return value
    if isinstance(value, dict):
        approver_value = value.get("approver")
        approver: UserRef | None
        if isinstance(approver_value, UserRef):
            approver = approver_value
        elif isinstance(approver_value, dict):
            approver = UserRef(
                id=str(approver_value.get("id") or ""),
                display_name=str(approver_value.get("display_name") or ""),
                roles=approver_value.get("roles") or (),
            )
        else:
            approver = None
        return ApprovalRequest(approved=bool(value.get("approved", False)), approver=approver)
    return ApprovalRequest(approved=False, approver=None)


def _evaluate_approver(*, requestor_id: str, approver: UserRef) -> PolicyDecision:
    """Approve the approver identity (separation of duties + permission).

    Returns a :class:`PolicyDecision` whose ``allowed`` flag tells the
    approval node whether to proceed. The reason is set to
    ``approval-self-or-unauthorized`` on both the self-approval and
    missing-permission paths because the public surface treats them as
    a single refusal (and the audit role_context + actor reveal which
    case fired).
    """
    if approver.id == requestor_id:
        return PolicyDecision(allowed=False, reason=AuditReason.APPROVAL_SELF_OR_UNAUTHORIZED)
    if not any(role.allows(APPROVER_PERMISSION) for role in approver.roles):
        return PolicyDecision(allowed=False, reason=AuditReason.APPROVAL_SELF_OR_UNAUTHORIZED)
    return PolicyDecision(allowed=True, reason=AuditReason.APPROVAL_AUTHORIZED)


def _build_audit_record(
    *,
    actor: ActorRef,
    action: str,
    decision: PolicyDecision,
    session_id: str,
    role_context: tuple[str, ...],
    clock: Callable[[], datetime],
) -> AuditRecord:
    return AuditRecord(
        id=new_audit_id(),
        actor=actor,
        action=action,
        decision=decision,
        timestamp=clock(),
        role_context=role_context,
    )


def _serialize_audit(record: AuditRecord) -> dict[str, Any]:
    """Serialize an :class:`AuditRecord` to a plain dict for state checkpoints.

    LangGraph's msgpack-backed checkpoint serializer refuses to
    serialize arbitrary domain dataclasses. The audit record is broken
    down to primitives so the state survives a pause/resume cycle
    without warnings.
    """
    return {
        "id": record.id,
        "actor_id": record.actor.id,
        "actor_kind": record.actor.kind,
        "action": record.action,
        "decision": {
            "allowed": record.decision.allowed,
            "reason": record.decision.reason,
            "required_permission": (
                record.decision.required_permission.name
                if record.decision.required_permission is not None
                else None
            ),
        },
        "timestamp": record.timestamp.isoformat(),
        "role_context": list(record.role_context),
    }


__all__ = [
    "APPROVER_PERMISSION",
    "ApprovalRequest",
    "InvestigationState",
    "build_investigation_graph",
    "sweep_stale_pauses",
]


# --------------------------------------------------------------------------- #
# Paused-graph TTL sweeper (CRIT-6)
# --------------------------------------------------------------------------- #


def sweep_stale_pauses(
    graph: Any,
    *,
    thread_ids: list[str],
    ttl_seconds: int,
    clock: Callable[[], datetime] | None = None,
) -> int:
    """Finalize paused graph threads older than ``ttl_seconds``.

    The CRIT-6 fix addresses the orphan-handling gap in the default
    :class:`InMemorySaver`: a paused investigation that nobody resumes
    sits in the checkpointer forever. This sweeper scans the supplied
    thread ids, identifies the ones that are still paused, compares
    the pause timestamp against the TTL, and resumes the stale ones
    with a denial decision so the finalize node records
    ``approval-timeout`` and the audit trail captures the abandonment.

    Returns the number of threads swept. Threads that are not paused
    (already finalized, never started, or resumed) are skipped.
    """
    now = (clock or (lambda: datetime.now(UTC)))()
    swept = 0
    for thread_id in thread_ids:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        if snapshot is None:
            continue
        # The thread is paused if the next node to run is the approval
        # node (the snapshot carries the ``next`` channel when the
        # graph is interrupted). If it's already finalized, skip.
        if not snapshot.next:
            continue
        # Compare the checkpoint timestamp against the TTL. LangGraph
        # stores ``created_at`` on each checkpoint tuple; the snapshot
        # exposes it as ``snapshot.created_at``.
        created_at = getattr(snapshot, "created_at", None)
        if created_at is None:
            # No timestamp available: be conservative and skip the
            # thread rather than risk sweeping an active one.
            continue
        age_seconds = (now - _as_utc(created_at)).total_seconds()
        if age_seconds < ttl_seconds:
            continue
        # Resume the thread with a denial. The approval node records
        # the refusal as a system-level decision and the finalize node
        # records the ``approval-timeout`` reason.
        graph.invoke(
            Command(
                resume=ApprovalRequest(
                    approved=False,
                    approver=_SYSTEM_APPROVER,
                ),
            ),
            config=config,
        )
        swept += 1
    return swept


def _as_utc(value: Any) -> datetime:
    """Coerce a timestamp to a UTC ``datetime`` for arithmetic.

    LangGraph checkpoints surface ``created_at`` as either a string
    (ISO 8601) or a ``datetime`` depending on the serializer version.
    Arithmetic against a timezone-aware ``now`` requires both sides
    to be aware datetimes.
    """
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
