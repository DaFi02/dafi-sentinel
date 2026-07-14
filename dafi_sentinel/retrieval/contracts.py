from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from dafi_sentinel.domain.models import Document, EvidenceRef


@runtime_checkable
class RetrievalIndex(Protocol):
    def search(self, query: str, limit: int) -> list[EvidenceRef]: ...


@dataclass(frozen=True)
class InMemoryRetrievalIndex:
    """Recall-only, order-stable in-memory retrieval index.

    R3 F24: the 4R review caught that the in-memory index's ranking
    contract was undocumented. This class is a structural
    implementation of :class:`RetrievalIndex` and ships with the
    following guarantees:

    * **Recall-only**: a document is included if ANY query term
      appears in its ``title`` or ``body`` (case-insensitive). The
      index does not implement BM25, cosine similarity, or any
      other relevance model — it is a simple recall filter. A
      future Postgres-backed ``RetrievalIndex`` may use a real
      scoring model; the contract only requires the evidence id
      and source to come back.
    * **Order-stable**: results are returned in the iteration order
      of ``self.documents``. The workbench service and the
      orchestration graph rely on the order being deterministic so
      replay-based review can reconstruct the cited evidence
      sequence. A future ranking model must preserve this
      contract (a stable secondary sort on top of the new score
      is acceptable).
    * **Bounded by ``limit``**: the result list is at most ``limit``
      entries. The implementation returns early once the limit is
      hit so very large document sets do not pay a full scan.

    The frozen dataclass keeps the document set immutable; callers
    that need to update the index construct a new instance with
    the revised tuple (the :class:`WorkbenchService` either seeds
    a fresh instance via :meth:`_index` or accepts an injected
    index — see ``dafi_sentinel.api.services``).
    """

    documents: tuple[Document, ...]

    def search(self, query: str, limit: int) -> list[EvidenceRef]:
        terms = {term.lower() for term in query.split() if term.strip()}
        if not terms or limit <= 0:
            return []

        results: list[EvidenceRef] = []
        for document in self.documents:
            haystack = f"{document.title} {document.body}".lower()
            if any(term in haystack for term in terms):
                results.extend(EvidenceRef(evidence_id, document.source) for evidence_id in document.evidence_ids)
            if len(results) >= limit:
                return results[:limit]
        return results
