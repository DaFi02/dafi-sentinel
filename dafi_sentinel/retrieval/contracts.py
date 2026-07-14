from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from dafi_sentinel.domain.models import Document, EvidenceRef


@runtime_checkable
class RetrievalIndex(Protocol):
    def search(self, query: str, limit: int) -> list[EvidenceRef]: ...

@dataclass(frozen=True)
class InMemoryRetrievalIndex:
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
