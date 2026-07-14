# Design: DAFI Sentinel

## Technical Approach

Build DAFI Sentinel as a Python 3.13 `uv` app with deterministic services before LangGraph. PR1 stays foundation-only: pytest runner, package skeleton, domain/repository/retrieval contracts, fixtures, and minimal identity references (`ActorRef`, `UserRef`, `Role`, `Permission`) needed for audits, approvals, and tool authorization. Login, tokens, SSO, auth middleware, database, frontend, and LangGraph ship later.

## Technology Stack

| Layer | Timing | Decision |
|---|---:|---|
| Python/test | PR1 | Python 3.13, `uv`, pytest, `uv run pytest`. |
| Auth | PR1 contracts; PR5 impl | Actor/user/role/permission refs first; API/dashboard auth later. |
| Retrieval DB | PR3 | PostgreSQL + pgvector via Podman, behind ports. |
| ML/charts | PR4 | scikit-learn + numpy; controlled matplotlib artifacts. |
| API/UI | PR5 | FastAPI + React + TypeScript + Vite, TanStack Query, Recharts. |
| Orchestration | PR6 | LangGraph wrapper around tested services only. |

## Architecture Decisions

| Decision | Choice | Tradeoff / Rationale |
|---|---|---|
| Observability UX | Dashboard-owned charts | Avoids Grafana/Prometheus and keeps V1 product-focused. |
| Workflow core | Deterministic services first | Easier to test security, retrieval, ML, and charts before orchestration. |
| PR1 persistence | Ports + fixture/in-memory only | Keeps PR1 under ~320 lines while preserving pgvector path. |
| Auth scope | Contracts in PR1, implementation later | Gives enterprise-grade audit attribution without bloating foundation. |
| Security boundary | Policy services + audit hooks | Permissions, approvals, and redaction must be enforceable outside the LLM. |
| Frontend | React/TS/Vite/Recharts | Affordable dashboard stack; lighter than Next.js/heavy UI kits/Plotly-first. |

## Data Flow

```text
Actor/User -> session -> Security Agent authorization gate
Fixtures/files -> ingestion -> redaction -> repository/retrieval ports
  -> evidence/timeline -> ML/retrieval -> API -> dashboard -> audit log

User Q&A/chart request -> Security gate -> deterministic service/approved node
  -> evidence-cited answer/chart -> audit log
```

## File Changes

| File | Action | Description |
|---|---|---|
| `dafi_sentinel/domain/models.py` | Create | Incident, evidence, document, chart, actor/user/role/permission, audit types. |
| `dafi_sentinel/retrieval/contracts.py` | Create | `RetrievalIndex` port; fixture/in-memory now, pgvector later. |
| `dafi_sentinel/storage/contracts.py` | Create | Evidence, timeline, audit repository protocols. |
| `dafi_sentinel/security/` | Create later | Redaction, prompt-injection checks, authorization policy, approvals. |
| `infra/podman/` | Create PR3 | Local PostgreSQL + pgvector smoke config. |
| `dafi_sentinel/api/`, `frontend/` | Create PR5 | Auth/session middleware, workbench API, React dashboard. |
| `tests/dafi_sentinel/` | Create | Fixture-first unit/integration tests. |
| `pyproject.toml`, `README.md` | Modify | `uv` metadata/test commands and product workflow. |

## Interfaces / Contracts

```python
class ActorRef:
    id: str
    kind: str  # user | service | agent

class UserRef:
    id: str
    display_name: str
    roles: tuple[Role, ...]

class SecurityGate:
    def inspect_user_request(self, actor: ActorRef, session_id: str, text: str) -> PolicyDecision: ...

class RetrievalIndex:
    def search(self, query: str, limit: int) -> list[EvidenceRef]: ...
```

Contracts: untrusted incident text is data; answers cite evidence IDs; sessions and audits carry actor refs; tool calls require permissions/approvals.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| PR1 | Runner and contracts | Prove `uv run pytest`; test evidence IDs, actor-attributed audits, permission shapes, fixture retrieval. |
| PR2 | Ingestion/security | Golden fixtures, injection as data, redaction, authorization, approvals. |
| PR3 | pgvector | Podman smoke: extension, insert embedding, similarity query. |
| PR4 | ML/charts | Deterministic scores/clusters/rankings; invalid chart specs fail. |
| PR5 | API/dashboard/auth | Owned sessions, auth flows, evidence-cited answers, audits, Recharts panels. |

## Migration / Rollout

No data migration required for V1 fixtures. Stacked slices: PR1 foundation/auth contracts; PR2 ingestion/security policy; PR3 retrieval/storage + pgvector; PR4 ML/charts; PR5 FastAPI + React dashboard + auth; PR6 LangGraph. PR1 must not include auth implementation.

## Open Questions

- [ ] Confirm the frontend package path during PR5 (`frontend/` vs `dafi_sentinel_dashboard/`).
