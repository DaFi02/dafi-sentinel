# Archive Report — podman-frontend-containerization

**Change**: podman-frontend-containerization (PR-B: Podman containerization of the frontend dev workflow)
**Archived**: 2026-08-23 → `openspec/changes/archive/2026-08-23-podman-frontend-containerization/`
**Main HEAD at close**: `5edc06c` · **Store mode**: hybrid (openspec filesystem + Engram mirrors) · **Project**: dafi-sentinel

## Verdict

**PASS** — archived after successful implementation and verification.

- Verification: 19/19 spec scenarios compliant (16 automated-test-backed, 3 drill-backed), zero CRITICAL, zero WARNING.
- Tasks: 13/13 `[x]` in the persisted tasks artifact (no stale checkboxes; no reconciliation needed).
- Delivery: force-chained stacked-to-main, 4 slices, every slice ≤ 400-line review budget.

## Merged PRs & Commits

Range `79f5245..5edc06c` on `main` (base before change: `537770e`):

| PR | Slice | Merge | Commits |
|----|-------|-------|---------|
| #8 | B1 — host hygiene, proxy env, context denylist/T7, resolution probe | `cbaa27a` | `79f5245` feat(podman): gate frontend context and proxy target behind env |
| #9 | B2 — Containerfile.web + compose web service + guards T5/T6/T8 | `3e6a937` | `162d2d4` feat(podman): add dev-server web image · `7614885` feat(podman): serve profile-gated dashboard via compose web service |
| #10 | B3 — freshness guard T9 + env-gated composed-boot E2E | `8ebb3da` | `c703d8d` test(podman): add freshness and composed-boot e2e guards · `4200124` test(podman): sweep e2e project images and scope t9 inputs to web |
| #11 | B4 — README podman-first + final validation | `5edc06c` | `aada875` docs(readme): make frontend workflows rootless-podman-first |

## Spec Sync Summary

Delta `specs/containerized-backend-workflow/spec.md` merged into main source of truth `openspec/specs/containerized-backend-workflow/spec.md`:

- **Action**: Updated (append-only merge, mirroring PR-A's verbatim-delta precedent).
- **ADDED**: 8 requirements, 19 scenarios — Web Dev Image Build Targets (2), Lock-Exact Frontend Dependency Sync (2), Frontend Context Excludes Host Artifacts (3), Env-Configurable Dev Proxy Target (2), Additive Profile-Gated Web Service (3), Frontend Container Guards Are CI-Safe (3), Env-Gated Composed-Boot E2E (3), Podman-First Frontend Documentation (1).
- **MODIFIED / REMOVED / RENAMED**: none.
- **Preserved**: all 8 pre-existing PR-A backend requirements untouched; post-merge total 16 requirements. Verified by requirement-count check.

## Deviations Ledger

All eight deviations adjudicated **consistent-with-amended-artifacts** by sdd-verify:

1. **D6 dual-profile standardization** — spec text mandates BOTH profiles; design FINDING 1 documents empirical `KeyError: 'api'`; T8 enforces render contract.
2. **Freshness Created-vs-mtime** (not ID equality) — strict ID equality proven unsound live (identical IDs reproduce under warm cache); spec letter describes exactly this comparison.
3. **Portable base stage** (apt/apk + useradd/adduser shim) — required so `NODE_TAG` override is genuinely true beyond Debian; documented inline in Containerfile.
4. **`chown /app` in dev leaf** — vite's TS-config loader writes bundled `.timestamp-*.mjs` beside the config; without dir ownership uid 10001 cannot serve. Documented inline.
5. **Remedy `rmi -f`** (vs plain rmi) — plain rmi only untags; `:local` guard tags co-pin identical content and cached rebuilds resurrect stale Created. Propagated consistently to guard message, tasks docstring, README.
6. **Proxied-route acceptance {200,401,405}** vs design's 401 guess — TestClient correction pre-run: unauthenticated GET `/sessions` → 405 from POST-only login route; proxy failures still fail via deadline retry.
7. **E2E image sweep added in review remediation** (`4200124`, +34 lines) — additive disk hygiene inside `try/finally`; residue contract preserved.
8. **T9 inputs scoped to web image** — matches spec R6 enumeration exactly; backend-Python exclusion documented in `_image_input_paths` docstring with operator guidance.

No silent deviations. No unresolved deviations.

## Residual Risks (from verify-report)

- **False-stale corner**: mtime-only bumps with fully-warm cache can rebuild a composed tag resurrecting the old object's Created until builder-cache prune or tag removal — fails SAFE toward rebuild.
- Backend-only edits can leave a stale composed `podman_api` undetected by T9 (documented scope decision; manual rebuild guidance in docstring).
- Gated E2E requires free ports 8000 AND 5173 (documented precondition; unique `-p` cannot free ports).

## Suggestions / Follow-ups (from verify-report)

1. Four behaviors have runtime/drill proof but no CI-repeatable automated test (NODE_TAG override, lock-drift failure, stale-image FAIL path, vite proxy prefix mapping) — cheap follow-ups exist (render-level proxy-map test; `--target deps` drift probe with stubbed lock).
2. Pre-existing `npm run build` TS6305 failure predates this change (proven at base `537770e`) — worth a dedicated fix.
3. Resolvable npm-lock drift slow-fails (≥14 min resolution latency) instead of fast-failing — structural to `npm ci`; carried open follow-up since B2.

## Engram Traceability (project dafi-sentinel)

| Artifact | Observation ID |
|----------|----------------|
| Exploration mirror | #2135 |
| Apply-progress mirror (final: all slices complete) | #2140 |
| Verify-report mirror | #2154 |
| Archive-report (this document) | saved to topic key `sdd/podman-frontend-containerization/archive-report` |

## SDD Cycle Complete

Change fully planned → specified → designed → tasked → applied (PRs #8–#11) → verified (PASS) → specs synced → archived.
