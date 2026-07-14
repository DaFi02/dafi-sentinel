from datetime import UTC, datetime

from dafi_sentinel.domain.models import (
    ActorRef,
    AuditRecord,
    ChartSpec,
    Document,
    Permission,
    PolicyDecision,
    RawIncidentRecord,
    RedactedIncidentRecord,
    Role,
    SourceMetadata,
    UserRef,
)
from dafi_sentinel.retrieval.contracts import InMemoryRetrievalIndex


def test_evidence_ids_are_stable_and_source_metadata_is_preserved():
    source = SourceMetadata(uri="fixtures/incidents.csv", row=2)
    raw = RawIncidentRecord(
        incident_id="inc-001",
        timestamp=datetime(2026, 7, 14, 10, 3, tzinfo=UTC),
        source=source,
        summary="Payment timeout errors crossed the alert threshold",
        fields={"severity": "critical"},
    )
    redacted = RedactedIncidentRecord.from_raw(raw, redacted_summary="Payment timeout [REDACTED]")

    assert raw.evidence_id == "ev-inc-001-fixtures-incidents-csv-row-2"
    assert redacted.evidence_ref.evidence_id == raw.evidence_id
    assert (redacted.source.uri, redacted.source.row) == ("fixtures/incidents.csv", 2)


def test_source_metadata_stable_part_uses_uri_when_location_is_absent():
    assert SourceMetadata(uri="fixtures/runbooks/Checkout Latency.md").stable_part == "fixtures-runbooks-checkout-latency-md"
    assert SourceMetadata(uri="fixtures/incidents.csv", offset=128).stable_part == "fixtures-incidents-csv-offset-128"


def test_audit_records_keep_actor_attribution_policy_and_chart_shape():
    permission = Permission(name="chart:request")
    role = Role(name="analyst", permissions=(permission,))
    actor = ActorRef(id="user-123", kind="user")
    user = UserRef(id="user-123", display_name="Incident Analyst", roles=(role,))
    decision = PolicyDecision(allowed=False, reason="approval required", required_permission=permission)
    chart = ChartSpec(kind="line", title="Error rate", x="timestamp", y="errors", evidence_ids=("ev-1",))
    audit = AuditRecord(
        id="audit-1",
        actor=actor,
        action="chart.request",
        decision=decision,
        timestamp=datetime(2026, 7, 14, 10, 5, tzinfo=UTC),
        role_context=(role.name,),
    )

    assert user.roles[0].allows("chart:request")
    assert (audit.actor.id, audit.decision.reason, audit.role_context) == ("user-123", "approval required", ("analyst",))
    assert chart.as_dashboard_payload() == {"kind": "line", "title": "Error rate", "x": "timestamp", "y": "errors", "evidence_ids": ["ev-1"]}


def test_retrieval_contract_returns_empty_and_fixture_document_results():
    empty_index = InMemoryRetrievalIndex(())
    assert empty_index.search("checkout", limit=3) == []

    doc = Document(
        id="doc-1",
        title="Checkout Latency Runbook",
        body="Compare checkout latency with deployment and payment dependency health.",
        source=SourceMetadata(uri="tests/dafi_sentinel/fixtures/runbook.md"),
        evidence_ids=("ev-inc-001-fixtures-incidents-csv-row-2",),
    )
    index = InMemoryRetrievalIndex((doc,))

    results = index.search("payment latency", limit=2)

    assert [result.evidence_id for result in results] == ["ev-inc-001-fixtures-incidents-csv-row-2"]
    assert results[0].source.uri == "tests/dafi_sentinel/fixtures/runbook.md"
