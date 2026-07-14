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
from langgraph.types import interrupt

from dafi_sentinel.api.services import WorkbenchService, new_audit_id
from dafi_sentinel.domain.models import ActorRef, AuditRecord, PolicyDecision
from dafi_sentinel.security.policy import SecurityGate
from dafi_sentinel.storage.contracts import AuditRepository


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
    """

    approved: bool
    approver_id: str = ""


# --------------------------------------------------------------------------- #
# Graph factory
# --------------------------------------------------------------------------- #


def build_investigation_graph(
    *,
    workbench: WorkbenchService,
    gate: SecurityGate,
    audits: AuditRepository,
    checkpointer: BaseCheckpointSaver | None = None,
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
    can pause and resume in tests. Production deployments should swap
    in a durable checkpointer (e.g., Postgres).
    """

    builder = StateGraph(InvestigationState)
    builder.add_node("inspect", _make_inspect_node(gate, audits))
    builder.add_node("retrieve", _make_retrieve_node(workbench, audits))
    builder.add_node("compose_answer", _make_compose_node())
    builder.add_node("request_approval", _make_approval_node(audits))
    builder.add_node("render_chart", _make_render_node(workbench, audits))
    builder.add_node("finalize", _make_finalize_node(audits))

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


def _make_inspect_node(gate: SecurityGate, audits: AuditRepository) -> Callable[[InvestigationState], dict[str, Any]]:
    def inspect(state: InvestigationState) -> dict[str, Any]:
        actor = _actor(state)
        decision = gate.inspect_user_request(actor, state["session_id"], state["question"])

        record = _build_audit_record(
            actor=actor,
            action="orchestration.inspect",
            decision=decision,
            session_id=state["session_id"],
            role_context=(state.get("owner_id") or "",),
        )
        audits.write_audit(state["session_id"], record)

        return {"audit_records": [_serialize_audit(record)]}

    return inspect


def _make_retrieve_node(workbench: WorkbenchService, audits: AuditRepository) -> Callable[[InvestigationState], dict[str, Any]]:
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
            reason=("evidence cited" if cited else "no supporting evidence"),
        )
        record = _build_audit_record(
            actor=actor,
            action="orchestration.retrieve",
            decision=decision,
            session_id=state["session_id"],
            role_context=(state.get("owner_id") or "",),
        )
        audits.write_audit(state["session_id"], record)

        return {
            "answer": answer,
            "cited": [ref.evidence_id for ref in cited],
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


def _make_approval_node(audits: AuditRepository) -> Callable[[InvestigationState], dict[str, Any]]:
    def request_approval(state: InvestigationState) -> dict[str, Any]:
        actor = _actor(state)
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

        decision = PolicyDecision(
            allowed=approval.approved,
            reason=(
                f"approved-by-{approval.approver_id}" if approval.approved else "approval-denied"
            ),
        )
        record = _build_audit_record(
            actor=actor,
            action="orchestration.approval",
            decision=decision,
            session_id=state["session_id"],
            role_context=(state.get("owner_id") or "",),
        )
        audits.write_audit(state["session_id"], record)

        return {
            "approval_granted": approval.approved,
            "approval_approver": approval.approver_id,
            "decision_reason": decision.reason,
            "audit_records": [_serialize_audit(record)],
        }

    return request_approval


def _make_render_node(workbench: WorkbenchService, audits: AuditRepository) -> Callable[[InvestigationState], dict[str, Any]]:
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
                action="orchestration.render_chart",
                decision=decision,
                session_id=state["session_id"],
                role_context=(state.get("owner_id") or "",),
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
                action="orchestration.render_chart",
                decision=decision,
                session_id=state["session_id"],
                role_context=(state.get("owner_id") or "",),
            )
            audits.write_audit(state["session_id"], record)
            return {
                "chart_png": None,
                "decision_reason": f"chart-render-failed: {exc}",
                "audit_records": [_serialize_audit(record)],
            }

    return render_chart


def _make_finalize_node(audits: AuditRepository) -> Callable[[InvestigationState], dict[str, Any]]:
    def finalize(state: InvestigationState) -> dict[str, Any]:
        actor = _actor(state)
        existing_reason = state.get("decision_reason")
        approved = bool(state.get("approval_granted"))

        if existing_reason in {"approval-denied", "no-supporting-evidence"} or str(existing_reason or "").startswith("chart-render-failed"):
            decision_reason = existing_reason or "approval-denied"
            decision = PolicyDecision(allowed=False, reason=decision_reason)
        elif not state.get("cited"):
            decision_reason = "no-supporting-evidence"
            decision = PolicyDecision(allowed=False, reason=decision_reason)
        elif approved:
            approver = state.get("approval_approver") or "unknown"
            decision_reason = f"approved-by-{approver}"
            decision = PolicyDecision(allowed=True, reason=decision_reason)
        else:
            decision_reason = existing_reason or "approval-denied"
            decision = PolicyDecision(allowed=False, reason=decision_reason)

        record = _build_audit_record(
            actor=actor,
            action="orchestration.finalize",
            decision=decision,
            session_id=state["session_id"],
            role_context=(state.get("owner_id") or "",),
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
    """Coerce the resume value (which round-trips through pickle) into an :class:`ApprovalRequest`."""
    if isinstance(value, ApprovalRequest):
        return value
    if isinstance(value, dict):
        return ApprovalRequest(
            approved=bool(value.get("approved", False)),
            approver_id=str(value.get("approver_id") or ""),
        )
    return ApprovalRequest(approved=False, approver_id="")


def _build_audit_record(
    *,
    actor: ActorRef,
    action: str,
    decision: PolicyDecision,
    session_id: str,
    role_context: tuple[str, ...],
) -> AuditRecord:
    return AuditRecord(
        id=new_audit_id(),
        actor=actor,
        action=action,
        decision=decision,
        timestamp=datetime.now(UTC),
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
    "ApprovalRequest",
    "InvestigationState",
    "build_investigation_graph",
]
