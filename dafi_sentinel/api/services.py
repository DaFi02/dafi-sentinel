"""In-memory implementations of the storage and retrieval contracts used by
the PR5 workbench service.

The PR1 storage contracts are protocol-only. The workbench service
provides in-memory implementations so the FastAPI app can be exercised
end-to-end without any external dependency. The implementations are
deterministic and easy to seed from tests.
"""

from __future__ import annotations

import base64
import secrets
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from dafi_sentinel.charts.renderer import render_chart
from dafi_sentinel.charts.validation import validate_chart_spec
from dafi_sentinel.domain.models import (
    AuditRecord,
    ChartSpec,
    Document,
    EvidenceRef,
    RedactedIncidentRecord,
)
from dafi_sentinel.ml.analysis import rank_similarity
from dafi_sentinel.retrieval.contracts import InMemoryRetrievalIndex
from dafi_sentinel.storage.contracts import AuditRepository, EvidenceRepository


def new_audit_id() -> str:
    """Return a unique audit record id.

    Re-execution of the same flow (e.g., re-invoking the LangGraph
    orchestration with the same ``session_id``) MUST NOT collide on the
    audit id. The 4R review (CRIT-5) caught two deterministic id schemes
    that fail under retry or FastAPI's sync threadpool; we use
    :func:`secrets.token_hex` so the id is unique per call and cheap to
    generate without dragging in a UUID dependency.
    """
    return f"audit-{secrets.token_hex(8)}"


@dataclass
class InMemoryEvidenceRepository:
    """Flattened evidence store keyed by evidence id.

    The ingestion service writes :class:`RedactedIncidentRecord` rows into
    a per-session list. The API needs a flat ``evidence_id -> record``
    view to support the ``GET /evidence/{evidence_id}`` endpoint. We
    keep the flat index in sync with the per-session list.
    """

    _records: dict[str, RedactedIncidentRecord] = field(default_factory=dict)
    _owners: dict[str, str] = field(default_factory=dict)

    def save(self, owner_id: str, record: RedactedIncidentRecord) -> EvidenceRef:
        evidence_id = record.evidence_ref.evidence_id
        self._records[evidence_id] = record
        self._owners[evidence_id] = owner_id
        return record.evidence_ref

    def get(self, evidence_id: str) -> RedactedIncidentRecord | None:
        return self._records.get(evidence_id)

    def owner_of(self, evidence_id: str) -> str | None:
        return self._owners.get(evidence_id)

    def list_for_owner(self, owner_id: str) -> tuple[RedactedIncidentRecord, ...]:
        return tuple(
            record
            for evidence_id, record in self._records.items()
            if self._owners.get(evidence_id) == owner_id
        )


@dataclass
class InMemoryAuditRepository:
    """Audit repository that records every decision in memory.

    Stores a chronological list and an index keyed by ``actor_id`` so the
    API can serve ``GET /audits`` cheaply. The repository is shared
    between the API and the security gate; the gate keeps writing to its
    own ``AuditSink`` for policy decisions while the API writes its own
    audit records for login/logout/Q&A/chart actions.
    """

    _records: list[AuditRecord] = field(default_factory=list)
    _by_actor: dict[str, list[str]] = field(default_factory=dict)

    def write_audit(self, session_id: str, record: AuditRecord) -> None:
        self._records.append(record)
        self._by_actor.setdefault(record.actor.id, []).append(record.id)

    def list_for_actor(self, actor_id: str) -> tuple[AuditRecord, ...]:
        ids = self._by_actor.get(actor_id, [])
        index = {record.id: record for record in self._records}
        return tuple(index[record_id] for record_id in ids if record_id in index)

    def all(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)


@dataclass(frozen=True)
class CitedEvidenceWithScore:
    """Cited evidence paired with the ML ranker score that selected it.

    The score is the cosine similarity produced by
    :func:`dafi_sentinel.ml.analysis.rank_similarity`. Surfacing it on the
    response (instead of the prior hardcoded ``0.0``) is required by the
    ``ml-incident-analysis`` spec scenario 'Rank similar evidence'.
    """

    ref: EvidenceRef
    score: float


@dataclass
class WorkbenchService:
    """Glue between the FastAPI app and the deterministic services.

    The service composes the existing PR1/PR2/PR3/PR4 services so the
    FastAPI handlers stay thin. Every method that performs a stateful
    action also writes an :class:`AuditRecord` to the shared audit
    repository.
    """

    evidence: InMemoryEvidenceRepository
    audits: AuditRepository
    documents: tuple[Document, ...] = ()

    def _index(self) -> InMemoryRetrievalIndex:
        return InMemoryRetrievalIndex(self.documents)

    def seed_documents(self, documents: Sequence[Document]) -> None:
        self.documents = tuple(documents)

    # ------------------------------------------------------------------ #
    # Evidence
    # ------------------------------------------------------------------ #

    def list_owned_evidence(self, owner_id: str) -> tuple[RedactedIncidentRecord, ...]:
        return self.evidence.list_for_owner(owner_id)

    def get_evidence(self, owner_id: str, evidence_id: str) -> RedactedIncidentRecord:
        record = self.evidence.get(evidence_id)
        if record is None:
            raise LookupError(f"evidence not found: {evidence_id}")
        owner = self.evidence.owner_of(evidence_id)
        if owner != owner_id:
            raise PermissionError(f"actor {owner_id!r} does not own evidence {evidence_id!r}")
        return record

    # ------------------------------------------------------------------ #
    # Q&A
    # ------------------------------------------------------------------ #

    def answer_question(
        self,
        *,
        actor_id: str,
        owner_id: str,
        session_id: str,
        question: str,
        limit: int,
    ) -> tuple[str, tuple[CitedEvidenceWithScore, ...]]:
        """Compose the retrieval port with the PR4 ML ranker.

        The retrieval port returns the candidate evidence set; the
        ranker orders them deterministically and produces a cosine
        similarity score per match. If no evidence supports the question,
        the answer is "unknown" and the audit log records the unanswered
        question.
        """
        candidates = self._index().search(question, limit=limit)
        cited: tuple[CitedEvidenceWithScore, ...]
        if not candidates:
            answer = "unknown"
            cited = ()
        else:
            # Build the records set the ranker can score against.
            records = self._records_for(candidates)
            ranked = rank_similarity(question, records, seed=0)
            cited = tuple(
                CitedEvidenceWithScore(
                    ref=EvidenceRef(
                        evidence_id=match.evidence_id,
                        source=self.evidence.get(match.evidence_id).source,  # type: ignore[union-attr]
                    ),
                    score=match.score,
                )
                for match in ranked
            )
            answer = self._compose_answer(question, cited)

        self._record_audit(
            actor_id=actor_id,
            session_id=session_id,
            action="qa.answer",
            allowed=bool(cited),
            reason=("evidence cited" if cited else "no supporting evidence"),
            role_context=(owner_id,),
        )
        return answer, cited

    def _records_for(self, evidence_refs: Sequence[EvidenceRef]) -> tuple[RedactedIncidentRecord, ...]:
        records: list[RedactedIncidentRecord] = []
        for ref in evidence_refs:
            record = self.evidence.get(ref.evidence_id)
            if record is not None:
                records.append(record)
        return tuple(records)

    @staticmethod
    def _compose_answer(
        question: str, cited: Sequence[CitedEvidenceWithScore]
    ) -> str:
        if not cited:
            return "unknown"
        evidence_list = ", ".join(item.ref.evidence_id for item in cited)
        return f"based on {evidence_list}: {question.strip()}"

    # ------------------------------------------------------------------ #
    # Charts
    # ------------------------------------------------------------------ #

    def render_chart(
        self,
        *,
        actor_id: str,
        owner_id: str,
        spec: ChartSpec,
        data: Sequence[tuple[object, object]],
    ) -> bytes:
        validate_chart_spec(spec)
        png_bytes = render_chart(spec, data)

        self._record_audit(
            actor_id=actor_id,
            session_id="chart",
            action="chart.render",
            allowed=True,
            reason=f"chart {spec.kind} rendered with {len(spec.evidence_ids)} evidence ids",
            role_context=(owner_id,),
        )
        return png_bytes

    # ------------------------------------------------------------------ #
    # Audits
    # ------------------------------------------------------------------ #

    def list_audits(self, owner_id: str) -> tuple[AuditRecord, ...]:
        # The store returns chronological records for the actor.
        return self.audits.list_for_actor(owner_id)  # type: ignore[attr-defined]

    def record_login(self, *, actor_id: str, session_id: str) -> None:
        self._record_audit(
            actor_id=actor_id,
            session_id=session_id,
            action="session.login",
            allowed=True,
            reason="login succeeded",
            role_context=(),
        )

    def record_logout(self, *, actor_id: str, session_id: str) -> None:
        self._record_audit(
            actor_id=actor_id,
            session_id=session_id,
            action="session.logout",
            allowed=True,
            reason="logout succeeded",
            role_context=(),
        )

    def _record_audit(
        self,
        *,
        actor_id: str,
        session_id: str,
        action: str,
        allowed: bool,
        reason: str,
        role_context: tuple[str, ...],
    ) -> None:
        from dafi_sentinel.domain.models import ActorRef, PolicyDecision

        record = AuditRecord(
            id=new_audit_id(),
            actor=ActorRef(id=actor_id, kind="user"),
            action=action,
            decision=PolicyDecision(allowed=allowed, reason=reason),
            timestamp=datetime.now(UTC),
            role_context=role_context,
        )
        self.audits.write_audit(session_id, record)


def png_to_base64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def base64_to_png(payload: str) -> bytes:
    return base64.b64decode(payload.encode("ascii"))


@dataclass
class RecentEvidenceCache:
    """Tiny LRU-ish helper that keeps the most recent evidence ids in
    stable order. Currently unused by the workbench surface but kept for
    testability of session-relative evidence lists."""

    capacity: int = 32
    _items: deque[str] = field(default_factory=deque)

    def push(self, evidence_id: str) -> None:
        if evidence_id in self._items:
            self._items.remove(evidence_id)
        self._items.append(evidence_id)
        while len(self._items) > self.capacity:
            self._items.popleft()

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._items)
