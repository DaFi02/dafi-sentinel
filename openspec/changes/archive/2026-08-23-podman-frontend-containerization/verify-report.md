# Verification Report — podman-frontend-containerization

**Change**: podman-frontend-containerization (all 4 slices merged: PR #8→#11, main HEAD `5edc06c`)
**Spec**: `openspec/changes/podman-frontend-containerization/specs/containerized-backend-workflow/spec.md` (R1–R8, 19 scenarios)
**Mode**: Strict TDD · **Verifier**: sdd-verify executor · **Date**: 2026-08-23
**Evidence policy**: every battery below was re-executed by the verifier in this session. Prior apply reports were used as claims to check, never as proof.

## Verdict

**PASS** — 19/19 scenarios compliant (16 backed by automated tests green in the verifier's own runs; 3 backed by live drills re-executed or structurally verified this session). Zero CRITICAL, zero WARNING. All eight known deviations adjudicated **consistent-with-amended-artifacts**.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 13 (Phases 1–9) |
| Tasks complete | 13 `[x]` |
| Tasks incomplete | 0 |
| Slices merged | 4/4 (#8 B1, #9 B2, #10 B3, #11 B4) |

## Build & Tests Execution (verifier's own runs)

**Build/type-check**: ➖ Python build N/A · frontend `tsc --noEmit` fails with TS6305 but **proven pre-existing** (identical failure reproduced at base commit `537770e` in an isolated worktree; `npm run build` is not part of this change's test surface).

| # | Command (run by verifier) | Result |
|---|---|---|
| 1 | `uv run pytest` (full default suite) | ✅ **278 passed, 2 skipped, 5 xpassed** in 193.25s, exit 0. Skips = pgvector-smoke gate + composed-E2E gate (`DAFI_COMPOSED_E2E != 1`); xpasses = intentional redaction flips. Matches apply baseline exactly. |
| 2 | `uv run pytest tests/dafi_sentinel/test_container_workflow.py -v` (enforce mode) | ✅ **12 passed, 1 skipped** in 99.61s — T0–T4 + T5/T6/T7/T8 + select_stale units + T9 all green with podman 5.x live; skip = E2E gate only. |
| 3a | D10 cleanup then `cd frontend && npm run test` (env unset) | ✅ **33 passed / 7 files** in 10.61s. Only tracked `.ts` on disk post-cleanup. |
| 3b | `DAFI_API_PROXY_TARGET=http://api:8000 npm run test` | ✅ **33 passed / 7 files** in 10.73s — unset-var behavior invariant (R4). |
| 4 | `DAFI_COMPOSED_E2E=1 … -k e2e -v` (ports verified free first) | ✅ **PASSED in 32.18s** — real postgres→api→web boot; `:8000/docs` 200, `:5173` HTML `id="root"`, proxied `/sessions` answered through vite proxy. |
| 5 | Teardown residue queries after #4 | ✅ ZERO containers/networks/images matching `dafi-composed-e2e`. |
| 6 | Podman-less simulation (PATH-shadowed env hiding `podman` + `podman-compose`) | ✅ **4 passed, 9 skipped with reasons, exit 0 in 0.08s** — static guards (T0/T7) + pure-core units stay always-on; all podman/compose guards skip cleanly (R6 "Skips without podman"). |
| 7 | Partial shadow (only `podman-compose` hidden) | ✅ T8/E2E skip "podman-compose not available"; T5/T6/T9 still enforce and pass. |
| 8 | **Staleness drill (reversible)**: bump input mtime → run T9 → restore mtime → rerun | ✅ Stale state: **FAILED naming both tags** `['podman_api', 'podman_web']` with exact `podman rmi -f … up -d --build` remedy. Restored: PASSED. Tree clean after. |
| 9 | **Lock-drift drill (reversible)**: inject bogus dep into `package.json`, build deps target | ✅ `npm ci` fails npm 404 at the deps stage → build aborts; lockfile never regenerated. Manifest restored byte-identical (git diff empty). |
| 10 | Absent-tag tolerance check | ✅ With no `localhost/podman_*` images present, T9 passes podman-present sans stack (confirms tolerant-pass semantics before drill #8). |
| 11 | Slice diff audit (`git diff --numstat` across merge boundaries) | ✅ B1 94, B2 211, B3 287 (= c703d8d +253 plus review-remediation 4200124 +34), B4 95 — all ≤ 400-line budget. |

Static checks (read/grep by verifier): compose `web` block loopback-only `127.0.0.1:5173:5173`, zero `volumes:`, `depends_on.api service_started`, canonical dual-profile header comment ✅ · `Containerfile.web` stages `base→deps→dev` (dev LAST), `ARG NODE_TAG=22-bookworm-slim`, uid/gid 10001, manifests-first COPY, `npm ci` + `npm-cache` mount, `USER 10001`, CMD `npm run dev -- --host 0.0.0.0 --strictPort` ✅ · `frontend/.containerignore` full D2 denylist incl. self-denial ✅ · README L247 canonical command byte-exact vs spec scenario, `rmi -f` remedy block (L280–281), E2E gate doc with port precondition (L284–291), six-pattern shadow WARNING with zsh caveat (L297–311), host-Node demoted to Fallback (L313+) ✅.

## Spec Compliance Matrix

Statuses: ✅ COMPLIANT = automated covering test green in verifier's run · ✅ᵈ = COMPLIANT via live drill (runtime-proven, not CI-repeatable — see Coverage gaps).

| Req | Scenario | Covering evidence | Result |
|-----|----------|-------------------|--------|
| R1 | Default build serves dashboard (uid 10001 vite) | `test_t5_web_dev_target_builds_and_runs_as_uid_10001` (enforce run ✅); serving+HMR proven live (apply B4 WS-101 probe; verifier's E2E `:5173` 200 `id="root"`) | ✅ |
| R1 | Node tag overridable | Apply-time drill `NODE_TAG=22-alpine` rc 0 (221 pkgs, musl set); portable apt/apk+useradd/adduser shim inspected by verifier | ✅ᵈ |
| R2 | Consistent manifests install reproducibly | `test_t6_web_image_suite_passes_in_image` — in-image `npm ci` green (enforce run ✅) | ✅ |
| R2 | Lock drift fails build | **Verifier's own drill #9 today**: npm 404 → deps stage aborts, lock untouched | ✅ᵈ |
| R3 | Host node_modules never leaks | `test_t7_…denylist_blocks_host_artifacts` (green in runs 1/2/6) + T5 context-root build ✅ | ✅ |
| R3 | Tracked configs beat emitted artifacts | T7 asserts emitted `.js`/`.d.ts` denials (✅); in-image half via T5/T6 (✅) | ✅ |
| R3 | Cleanup restores host parity | D10 cleanup executed before verifier's vitest runs (✅ 33/33 on `.ts` sources) | ✅ |
| R4 | Unset var keeps host behavior | Code-inspected default literal (`vite.config.ts` L21); vitest 33/33 under BOTH env states (runs 3a/3b) | ✅ |
| R4 | Compose routes proxy to api | Verifier's gated E2E run #4: proxied `/sessions` answered by api container through vite proxy | ✅ |
| R5 | Plain startup unchanged | `test_t8…`: plain render lacks `web` (enforce run ✅); live postgres-only regression at apply (B4 check 3) | ✅ |
| R5 | Profile exposes loopback dashboard | T8 `ports == ["127.0.0.1:5173:5173"]`, zero volumes (✅); live `:5173` 200 in E2E run #4 | ✅ |
| R5 | Web implies api chain | T8 exact `{postgres, api, web}` render + `depends_on.api` (✅); chain order proven in E2E run #4 | ✅ |
| R6 | Skips without podman | **Verifier's PATH-shadowed run #6**: 4 passed / 9 skipped with reasons / exit 0 | ✅ |
| R6 | Guards enforce with podman | Enforce-mode run #2: build, uid, in-image suite, context, freshness all pass | ✅ |
| R6 | Stale image fails freshness guard | **Verifier's own drill #8**: FAILED naming both stale tags + `rmi -f` remedy; `_select_stale` unit tests pin semantics (✅) | ✅ᵈ |
| R7 | Gated off by default | Run #1 skip line `DAFI_COMPOSED_E2E != 1`; suite stays infra-free | ✅ |
| R7 | Gate proves api-to-web chain | **Verifier's live E2E run #4**: PASSED 32.18s over real ports incl. proxied route | ✅ |
| R7 | Teardown leaves no residue | **Verifier's own residue queries #5**: zero containers/networks/images | ✅ |
| R8 | Docs cover the dashboard chain | README canonical command byte-exact (L247); apply B4 copy-paste top-to-bottom battery from clean state | ✅ |

**Compliance summary**: 19/19 scenarios compliant (16 automated-test-backed, 3 drill-backed). No UNTESTED, no FAILING, no PARTIAL.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| R1 Web image targets | ✅ Implemented | 3-stage graph, dev leaf last, NODE_TAG ARG, uid 10001 leaf, strictPort CMD |
| R2 Lock-exact sync | ✅ Implemented | Manifests-first COPY, `npm ci` + cache mount, drift fails build (drilled) |
| R3 Context exclusions | ✅ Implemented | Dedicated `frontend` context; full denylist incl. self-denial; root-context trap avoided |
| R4 Proxy env contract | ✅ Implemented | Single `DAFI_API_PROXY_TARGET`, default literal, six explicit prefix refs |
| R5 Profile-gated web | ✅ Implemented | Loopback-only publish, no volumes, `service_started` dep, dual-profile standardization documented |
| R6 CI-safe guards | ✅ Implemented | No new markers (`--strict-markers` safe); which()-based skips proven; freshness per amended mechanism |
| R7 Env-gated E2E | ✅ Implemented | Gate + unique `-p` project + try/finally teardown + image sweep + success-gated residue assert |
| R8 Podman-first docs | ✅ Implemented | Dashboard chain leads; proxy contract table; remedy; E2E gate; shadow WARNING; fallback demoted |

## Design Coherence & Deviations Adjudication

All eight deviations from the mandate ruled:

| Deviation | Ruling | Basis |
|---|---|---|
| D6 dual-profile standardization | ✅ Consistent | Spec text itself mandates BOTH profiles (amended pre-tasks); design FINDING 1 documents the empirical `KeyError: 'api'` basis; T8 enforces the render contract. |
| Freshness Created-vs-mtime (not ID equality) | ✅ Consistent | Spec R6 letter describes exactly this comparison; falsifiable ID-equality fallback resolved live (identical IDs reproduced on cache ⇒ strict equality unsound). |
| Portable base stage (apt/apk shim) | ✅ Consistent | Required for spec R1-s2 (`NODE_TAG` override) to be genuinely true beyond Debian; slight extension of D9 letter, documented inline in Containerfile comments. |
| `chown /app` in dev leaf | ✅ Consistent | Vite's TS-config loader writes bundled `.timestamp-*.mjs` beside the config; without dir ownership USER 10001 cannot serve. T5/T6 prove uid operation. Documented inline. |
| Remedy `rmi -f` (vs task-literal plain rmi) | ✅ Consistent | Insufficiency drilled twice live (plain rmi only untags; `:local` guard tags co-pin identical content and cached rebuilds resurrect stale Created). Spec requires only "an rmi-rebuild remedy". Corrected string propagated consistently to guard message, tasks docstring, README. |
| Proxied-route acceptance {200,401,405} vs design's 401 guess | ✅ Consistent | Apply-time TestClient correction BEFORE the live run: unauthenticated GET `/sessions` → 405 from POST-only login route. All three statuses prove FastAPI answered through the proxy; proxy failures (502/504/refused/reset) still fail via deadline retry. |
| E2E image sweep added in review remediation (commit 4200124, +34 lines) | ✅ Consistent | Additive disk hygiene inside `try/finally`; residue contract preserved (assert still runs on primary success); explains the B3 numstat delta (253→287); slice stays ≤400. |
| T9 inputs scoped to web image (docstring honest) | ✅ Consistent | Spec R6 enumerates exactly those inputs (Containerfiles, package manifests/lockfiles, frontend configs, `frontend/src/**`). Backend-Python exclusion explicitly documented in `_image_input_paths` docstring with operator guidance. |

## TDD Compliance (Strict mode)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | B3 explicit "TDD Cycle Evidence" table in apply-progress; B1/B2 RED/GREEN recorded per-task in tasks.md; U4 declared STANDARD (docs slice, no new tests) — honest scoping. |
| All tasks have tests | ✅ | 9/13 tasks test-bearing; the other 4 are cleanup (1.1), transient probe (4.1), README (9.1), validation battery (9.2) — test-less by nature. |
| RED confirmed (tests exist & failed first) | ✅ | Recorded REDs: rg rc=1 (2.1); 1 failed file-missing (3.1); 2 failed pull-attempts (5.1); 1 failed no-web-render (6.1); 3 failed NameError (7.1). Test files verified present in codebase by verifier. |
| GREEN confirmed (tests pass now) | ✅ | Verifier's own executions: module 12/12 enforceable green; suites green (runs 1–3). |
| Triangulation adequate | ✅ | `_select_stale` ×2 value-varied units; E2E three distinct poll targets; staleness/absent/tie semantics pinned; drift + NODE_TAG + staleness drills add behavioral variance. |
| Safety Net for modified files | ✅ | Module counts recorded before each edit wave (5/5 → 6/6 → 9/9 → 13 items); full suite stayed green throughout slices. |

**TDD Compliance**: 6/6 checks passed.

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Static every-host guards | 2 (T0, T7) | 1 | pytest file-parse (no skipif) |
| Unit (pure core) | 2 (`_select_stale`) | 1 | pytest |
| Integration (subprocess/podman) | 8 (T1–T6, T8, T9) | 1 | pytest + podman/podman-compose |
| E2E (env-gated live compose boot) | 1 | 1 | pytest + urllib poller |
| Frontend component/jsdom (pre-existing, untouched by change) | 33 | 7 | vitest |
| **Total (this change)** | **13 module items** | **1** | |

Layer coverage matches design Testing Strategy exactly. No critical business logic relegated to unit-only while higher layers sit available — the chain is proven E2E.

## Changed File Coverage

Coverage analysis skipped — no coverage tool detected (pytest plugins: anyio/langsmith/timeout only; no pytest-cov; no vitest coverage wired). Informational, not blocking. Changed files are exercised near-exhaustively by the guard module itself (T7 parses the ignorefile; T5/T6 execute the image; T8 renders compose; T9/E2E exercise freshness/teardown paths including failure branches via drills).

## Assertion Quality

Audited all changed/added test code (`test_container_workflow.py` deltas): assertions are behavioral value assertions (`rc == 0` + stderr tails, `Config.User == "10001"`, `"passed" in stdout`, exact port-list equality, set-equality of rendered services, exact stale-list expectations, `'id="root"' in body`, status-membership acceptance sets, residue-empty assert). Zero tautologies, zero orphan-empty checks, zero ghost loops, zero mocks (real subprocesses end-to-end), no implementation-detail coupling (loopback string IS the spec'd contract).

**Assertion quality**: ✅ All assertions verify real behavior.

## Quality Metrics

**Linter (Python)**: ➖ Not configured (no ruff/flake8 config found). **Type checker (Python)**: ➖ Not configured. **Frontend**: `tsc --noEmit` ❌ TS6305 on `csp_toggle.test.ts` — **proven pre-existing** (reproduced identically at base `537770e`); outside change scope; SUGGESTION below.

## Issues Found

**CRITICAL**: None.
**WARNING**: None.
**SUGGESTION**:
1. Four behaviors have runtime/drill proof but no CI-repeatable automated test: NODE_TAG override (apply-drilled only), lock-drift failure (drilled twice), stale-image FAIL path (drilled; pure core unit-tested), vite proxy six-prefix mapping/default literal (code + compose-side E2E only). Cheap follow-ups exist (e.g., a render-level test parsing `vite.config.ts` proxy map; a `--target deps` drift probe using a stubbed lock).
2. Pre-existing `npm run build` TS6305 failure (project-references/composite quirk) predates this change; worth a dedicated fix.
3. Resolvable npm-lock drift slow-fails (≥14 min resolution latency) instead of fast-failing — structural to `npm ci`; carried open follow-up since B2.

## Residual Risks

- **False-stale corner**: under mtime-only bumps with fully-warm cache, a rebuilt composed tag can resurrect the old object's Created (guard `:local` tags co-pin content) until builder-cache prune or tag removal — fails SAFE toward rebuild; mechanics documented in README + apply B4.
- Backend-only edits can leave a stale composed `podman_api` undetected by T9 (documented scope decision; manual rebuild guidance in docstring).
- Gated E2E requires free ports 8000 AND 5173 (documented precondition; unique `-p` cannot free ports).
