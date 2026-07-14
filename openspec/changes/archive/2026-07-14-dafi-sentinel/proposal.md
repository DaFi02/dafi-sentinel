# Proposal: DAFI Sentinel

> **Archive status**: archived on 2026-07-14. HEAD at archive: `e96daa3`. See `archive-report.md` in this folder for the audit trail.

## Intent

Build a security-first AI incident investigation workbench. V1 turns seeded logs, alerts, deployments, tables, and later runbooks/documents into evidence-backed timelines, hypotheses, answers, and charts.

## Scope

### In Scope
- Deterministic ingestion, evidence IDs, redaction, timelines, audits.
- Product dashboard for investigations, evidence, hypotheses, audits, and charts.
- Authentication/user identity as a planned product capability for session ownership, audit attribution, role-based tool permissions, and human approvals.
- Security Agent boundaries: injection handling, redaction, authorization, permissions, approvals.
- scikit-learn analysis with stable fixtures.
- `uv` dependencies and `uv run pytest`.
- Podman PostgreSQL + pgvector for RAG/runbook/document retrieval after foundation.

### Out of Scope
- Grafana, Prometheus, external dashboards, or live monitoring dependencies.
- Cloud/SIEM/ticketing/tracing integrations, enterprise SSO, multi-tenant RBAC administration, external vector DBs, fine-tuned models, and remediation.
- Full authentication implementation in PR1.
- Database implementation in PR1.

## Capabilities

### New Capabilities
- `incident-data-ingestion`: Parse and normalize local incident datasets.
- `investigation-workbench`: Manage sessions, timelines, evidence, and charts.
- `security-agent`: Enforce redaction, prompt boundaries, identity-aware authorization, permissions, and approvals.
- `ml-incident-analysis`: Provide fixture-stable anomaly, clustering, similarity, and ranking behavior.
- `rag-document-retrieval`: Retrieve runbooks, documents, and evidence through pgvector ports.

### Modified Capabilities
- None; no existing OpenSpec capabilities are present.

## Approach

Keep deterministic Python services before scoped LangGraph. PR1 creates only the `uv` foundation: package skeleton, pytest runner, contracts, fixture/in-memory ports, and minimal identity/authorization domain references (`ActorRef`, `UserRef`, `Role`, `Permission`) when needed for audit/security models. Later slices add ingestion/security, Podman pgvector retrieval, ML/charts, API/dashboard authentication, then a small LangGraph wrapper.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `dafi_sentinel/` | New | Services, API, orchestration, dashboard. |
| `pyproject.toml` | Modified | Manage dependencies with `uv`; add pytest first. |
| `infra/podman/` | New | PostgreSQL + pgvector local infra after PR1. |
| `README.md` | Modified | Product story, Podman quickstart, no Grafana/Prometheus. |
| `openspec/specs/` | New | Add listed capability specs. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| V1 exceeds 400 changed lines | High | Use stacked chained PRs. |
| LangGraph sprawl | Medium | Keep business logic in deterministic services. |
| pgvector expands PR1 | Medium | Add it only after foundation. |
| Authentication expands PR1 | Medium | Limit PR1 to identity/authorization contracts; implement auth in a later API/dashboard/security slice. |
| Security claims lack proof | Medium | Require redaction, injection, permission, and audit tests. |

## Rollback Plan

Revert package, `uv` changes, README, Podman infra, and OpenSpec specs. PR1 has no database migration; later pgvector data is local and can be dropped with its Podman volume.

## Dependencies

- Python 3.13, `uv`, pytest, scikit-learn, charting, Podman, PostgreSQL, pgvector.

## Success Criteria

- [ ] Seeded incidents can be ingested, analyzed, questioned, charted, and audited.
- [ ] PR1 passes `uv run pytest` without PostgreSQL, pgvector, Grafana, or Prometheus.
- [ ] PR1 includes only minimal identity/authorization contracts, not login/session middleware.
- [ ] PostgreSQL + pgvector retrieval ships later with a focused Podman smoke test.
- [ ] Security Agent behavior is tested before user-facing agent workflows ship.
