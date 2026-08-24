# Proposal: Podman Containerization of Frontend Dev Workflow (PR-B)

Change: `podman-frontend-containerization` · Store: hybrid · Date: 2026-08-23

## Intent

PR-A containerized every backend workflow, but the dashboard still runs host-based with an unenforced Node runtime, and both PR-A carry-overs stay manual. This closes the Podman-first policy end-to-end. Measurable outcome: `podman-compose --profile api --profile web up -d` serves the EXISTING dashboard at http://127.0.0.1:5173 with zero host Node usage; the api→web chain is proven by an automated env-gated test.

## Scope

### In Scope
- Dev-server-only `web` service (vite + HMR in-container); UI untouched.
- `Containerfile.web`, dedicated frontend build context, `frontend/.containerignore`.
- Env-configurable dev proxy (`DAFI_API_PROXY_TARGET`).
- Guards extending T0–T4 pattern + stale-image freshness guard (carry-over #2).
- Env-gated composed-boot E2E `DAFI_COMPOSED_E2E=1` (carry-over #1).
- README frontend sections become Podman-first.

### Out of Scope
- Frontend redesign / new UI features (user-deferred).
- Production image build, static serving, nginx.
- Backend Python changes beyond compose wiring.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `containerized-backend-workflow`: ADD frontend requirements — web image targets, dedicated context denylist, proxy env contract, profile-gated loopback `web` (:5173), guard/E2E contracts, docs.

## Approach

| Area | Approach |
|---|---|
| Image | New `infra/podman/Containerfile.web`: multi-stage node (`ARG NODE_TAG=22-bookworm-slim`); deps stage `npm ci` + cache mount `id=npm-cache`; baked node_modules; non-root uid 10001; `dev` leaf |
| Context | Dedicated `../../frontend` context + denylist ignorefile (root ignorefile denies `frontend/` — repo-root context would COPY nothing) |
| Proxy | Single `DAFI_API_PROXY_TARGET` via `process.env` in `vite.config.ts` (default `http://127.0.0.1:8000`); compose sets `http://api:8000`; shared by all 6 prefixes |
| Compose | Profile-gated `web`: `127.0.0.1:5173:5173`, `depends_on: api: service_started`, mounts nothing; plain `up -d` stays postgres-only |
| Guards | Extend `test_container_workflow.py` (podman-dependent guards skipif no-podman; static context-denylist guard runs on every host): web build, uid, vitest-in-image; creation-time-vs-newest-input-mtime stale-image guard naming the stale tag with an `rmi`-rebuild hint |
| E2E | `DAFI_COMPOSED_E2E=1`: unique `-p` project name, api+web profiles, assert `:8000/docs` + `:5173` HTML + proxied route; `finally` teardown |
| Docs | README "Run the dashboard" (~L240), slice tests (~L263), container reference table |
| Gotcha | Task step `rm -f`-ing stale emitted `vite.config.{js,d.ts}` / `vitest.config.{js,d.ts}` AND `frontend/src/vite/*.{js,d.ts}` when `vite.config.ts` or `src/vite/**` changes (emitted `.js` shadows `.ts` on host runs) |

## Risks

| Risk | Sev | Mitigation |
|---|---|---|
| Stale gitignored vite/vitest `.js` shadow `.ts` edits locally | High | Delete/rebuild artifacts as explicit task step |
| Build-context trap (root ignore denies `frontend/`) | Med | Dedicated context + guard asserting copied files |
| podman-compose tag reuse replicates staleness for `_web`; `pull_policy` unverified | Med | Creation-time-vs-input-mtime freshness guard covers web; avoid pull_policy reliance |
| Single-profile `--profile web` crashes (podman-compose 1.6.0 never auto-enables depended-on services) | Resolved | All invocations standardized on `--profile api --profile web`; verified live on podman 5.8.4 + podman-compose 1.6.0 |
| HMR over published port; esbuild/@rollup native binaries | Low | Verify live once; apt limited to ca-certificates if needed |

## Delivery Forecast (400-line budget)

compose +25 · web Containerfile ~40 · ignorefile ~10 · vite config ~10 · guards +150 · README ~50 · SDD docs ~100 → single stacked-to-main slice **~300–385 lines**. Decision needed before apply: **No**. Chained PRs recommended: **No** — split infra/guards/docs force-chained only if apply exceeds ~385 lines. Budget risk: **Low**.

## Rollback Plan

Delete `Containerfile.web`, `frontend/.containerignore`, new guard tests; revert compose / vite.config.ts / README hunks. Additive and profile-gated: postgres-only default never regresses. No migrations, no production code touched.

## Dependencies

Podman 5.8.4 rootless + podman-compose 1.6.0 (proven); registry pull `node:22-bookworm-slim`.

## Success Criteria

- [ ] `--profile api --profile web up -d` serves http://127.0.0.1:5173 with working proxied API routes
- [ ] Plain `up -d` unchanged (postgres only)
- [ ] Default pytest passes infra-free; new guards skip without podman
- [ ] `DAFI_COMPOSED_E2E=1` proves api→web chain incl. proxy
- [ ] README frontend workflows are Podman-first
- [ ] Diff ≤400 lines or split into chained slices

## Proposal question round

Executor ran non-interactively; scope decisions pre-approved by user (dev-server-only, guard pattern, E2E in scope, :5173 loopback-only, exploration constraints binding). Flag corrections before spec phase.
