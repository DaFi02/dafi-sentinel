# Tasks: Podman Containerization of Frontend Dev Workflow (PR-B)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~365 code+guards+docs: U1 ≈34, U2 ≈137, U3 ≈90, U4 ≈55 (excl. ~100 SDD docs already on branch) |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes (forced: FORCE-CHAINED delivery; each slice ≤ ~140 lines) |
| Suggested split | PR-B1=U1 → PR-B2=U2 → PR-B3=U3 → PR-B4=U4 (serialized slices) |
| Delivery strategy | force-chained (binding session preflight) |
| Chain strategy | stacked-to-main |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low
```

Decision needed before apply: **No** — chain strategy fixed (force-chained, stacked-to-main); every slice stays far below the 400-line budget, so no `size:exception` is required. Total ~365 lines fits one PR, but FORCE-CHAINED delivery mandates sliced reviewable units anyway.

### Suggested Work Units

| Unit | Goal | Likely PR | Base / notes |
|------|------|-----------|--------------|
| 1 | Host hygiene + proxy env + context denylist/T7 + BLOCKING resolution probe (Phases 1–4) | PR-B1 | `podman-containerization/pr-b` @ `main@<sha at apply>` |
| 2 | `Containerfile.web` + compose `web` + guards T5/T6/T8 (Phases 5–6) | PR-B2 | Builds on U1 (probe result decides Containerfile location) |
| 3 | Freshness guard T9 + env-gated E2E (Phases 7–8) | PR-B3 | Verifies U1+U2 composed |
| 4 | README Podman-first + final validation (Phase 9) | PR-B4 | Independent of guard internals |

Publishing: each unit commits on `podman-containerization/pr-b`; open its PR via **GitHub MCP only** (never local push), base `main`. One open slice PR at a time; after PR N merges, continue on the branch so PR N+1's diff shows only unit N+1. Every PR carries the chained-pr "Chain Context" section (position, base, budget, 📍 diagram).

### Traceability Key (spec: specs/containerized-backend-workflow/spec.md)

R1 Web Image Targets · R2 Lock-Exact Sync · R3 Context Exclusions · R4 Proxy Env · R5 Profile-Gated Web · R6 CI-Safe Guards · R7 Composed-Boot E2E · R8 Podman Docs

## Phase 1 (Step 1, U1): Shadowing-Artifact Cleanup (D10) — 0 diff lines

- [x] 1.1 **Delete** emitted shadowing artifacts on host before any verification touching `frontend/vite.config.ts` or `src/vite/**`: `rm -f frontend/vite.config.{js,d.ts} frontend/vitest.config.{js,d.ts} frontend/src/vite/*.js frontend/src/vite/*.d.ts` (six patterns; `vitest.config.d.ts` never emitted — `rm -f` tolerates absence; NEVER assume counts). Repeat before every host-side verify in Phases 2–9. ▸ Verify: `cd frontend && npm run test` exits 0 (host vitest green, `.ts` sources resolve). ▸ Trace: R3 "Cleanup restores host parity". ▸ Rollback: none needed (gitignored regenerable artifacts only). ▸ Commit: none (no tracked change). ✅ Five artifacts existed and were deleted; vitest 33/33 green. Repeated before each host-side verify.

## Phase 2 (Step 2, U1): Env-Configurable Dev Proxy (D4) — ~4 lines

One work-unit commit (with Phase 3). ▸ Commit: `feat(podman): gate frontend context and proxy target behind env`

- [x] 2.1 **Modify** `frontend/vite.config.ts`: add `const API_TARGET = process.env.DAFI_API_PROXY_TARGET ?? "http://127.0.0.1:8000";` above `server`; point all SIX prefixes (`/sessions /evidence /qa /charts /roles /audits`) at `API_TARGET` (explicit entries, no loop magic; `csp-toggle.ts` `process.env` precedent — no `loadEnv`). RED proof: `rg -c 'DAFI_API_PROXY_TARGET' frontend/vite.config.ts` = 0 before edit. ▸ Verify (GREEN): `rg -c 'DAFI_API_PROXY_TARGET' frontend/vite.config.ts` ≥ 7 (const + 6 refs); `rg -n '127\.0\.0\.1:8000' frontend/vite.config.ts` matches ONLY the default line; re-run 1.1 deletion + `cd frontend && npm run test` exit 0 (unset-var host behavior byte-identical). ▸ Trace: R4 "Unset var keeps host behavior"; compose side proven in 6.2/8.1. ▸ Est: +4 lines. ✅ RED rc=1 (0 matches); GREEN: env literal on const line only; `rg -c 'API_TARGET'` = 7 (const + 6 refs — note: `rg -c` counts lines, and the six prefixes reference the const per D4, so the ≥-7 check applies to the const identifier); loopback literal only on line 21; vitest 33/33 unset-var.

## Phase 3 (Step 3, U1): Context Denylist + Static Guard T7 (D2) — ~30 lines, RED→GREEN same commit

- [x] 3.1 **RED — extend** `tests/dafi_sentinel/test_container_workflow.py` with always-on T7 (NO skipif — runs podman-less, restores PR-A every-host carve-out; T0 pattern): parse `frontend/.containerignore`, assert denials for `node_modules/`, `dist/`, `.vite/`, `coverage/`, `*.tsbuildinfo`, emitted root configs (`vite.config.js`, `vite.config.d.ts`, `vitest.config.js`, `vitest.config.d.ts`), `src/vite/*.js`, `src/vite/*.d.ts`, and SELF (`​.containerignore`). ▸ Verify: `uv run pytest tests/dafi_sentinel/test_container_workflow.py -k t7 -v` FAILS (file missing). ▸ Est: +18 lines. ✅ Test `test_t7_frontend_containerignore_denylist_blocks_host_artifacts` (named with the `t7` token so `-k t7` selects it; also asserts `dist-ssr/` per D2 full list); RED confirmed: 1 failed (file missing). Module safety net before edit: 5/5. GOTCHA found during final validation: unconditional existence assert broke T2's IN-IMAGE suite (root context denies `frontend/`, so `/app/frontend/.containerignore` never exists in-image) — fixed by mirroring T0's co-absence carve-out (`no .git ⇒ containerized exec ⇒ skip`); host stays always-on-fail.
- [x] 3.2 **GREEN — create** `frontend/.containerignore` with the exact D2 denylist above (self-denying; gains `Containerfile.web` ONLY if the 4.1 probe fallback triggers). ▸ Verify: T7 passes podman-less: `uv run pytest tests/dafi_sentinel/test_container_workflow.py -k t7 -v` exit 0. ▸ Trace: R3 "Host node_modules never leaks" + "Tracked configs beat emitted artifacts" (static half; in-image proof via T5 build in 5.2). ▸ Est: +12 lines. ✅ Created exact D2 denylist (+ comments); `-k t7` exit 0 (1 passed, 0.04s, podman-less).

## Phase 4 (Step 4, U1): BLOCKING Dockerfile-Resolution Probe (D6 FINDING 4) — 0 net lines, gates ALL dependent work

- [x] 4.1 **Probe** out-of-context `dockerfile:` build resolution BEFORE any dependent work: stub two-line `FROM node:22-bookworm-slim` `infra/podman/Containerfile.web` + temporary compose `web` block (exact D6 shape) → `podman-compose -f infra/podman/compose.yaml --profile api --profile web build web` MUST exit 0. On failure: apply pre-agreed D6 fallback — move file to `frontend/Containerfile.web`, compose `dockerfile: Containerfile.web`, add `Containerfile.web` to the 3.2 denylist — and record DEVIATION (Phases 5–6 paths shift accordingly). ▸ Verify: probe build rc 0 (out-of-context proven) OR fallback build rc 0 (in-context, definitionally safe). ▸ Trace: gate for R1/R5 implementation; risk register "Out-of-context `dockerfile:` resolution". ▸ Rollback: stub deleted/replaced in Phase 5. ▸ Est: 0 net (transient). ✅ OUTCOME: probe build rc 0 — out-of-context `dockerfile: ../infra/podman/Containerfile.web` resolves correctly on podman 5.8.4 + podman-compose 1.6.0 (tagged localhost/podman_web). NO fallback, NO DEVIATION: Phase 5 keeps `infra/podman/Containerfile.web`, denylist unchanged, Phases 5–6 paths stand. Stub file + compose block + probe image all removed (no residue). Bonus evidence: tag confirms D7 `<project>` derivation = `podman` for T9.

## Phase 5 (Step 5, U2): Web Image + Guards T5/T6 (D1–D3, D5, D9) — ~75 lines, RED→GREEN same commit

One work-unit commit. ▸ Commit: `feat(podman): add dev-server web image and profile-gated compose service` ▸ Unit rollback: revert commit (deletes Containerfile.web + new guard blocks).

- [x] 5.1 **RED — extend** `test_container_workflow.py`: T5 `@requires_podman` — build `podman build -f infra/podman/Containerfile.web --target dev -t dafi-sentinel-web:local frontend` rc 0 (cwd repo root; context root carries the ignorefile) + `Config.User == "10001"`; T6 `@requires_podman` — `podman run --rm dafi-sentinel-web:local npm run test` rc 0 + `passed` in stdout (T2 analog; vitest infra-free; timeout=BUILD_TIMEOUT/RUN_TIMEOUT reuse; NO new markers). ▸ Verify: both FAIL against the 4.1 stub (User assertion/build COPY errors). ▸ Est: +35 lines. ✅ Tests named `test_t5_web_dev_target_builds_and_runs_as_uid_10001` / `test_t6_web_image_suite_passes_in_image` (`-k "t5 or t6"` token convention); RED confirmed 2 failed (missing Containerfile ⇒ pull attempts fail). Module safety net before edits: 6/6.
- [x] 5.2 **GREEN — create** real `infra/podman/Containerfile.web` (location per 4.1 outcome): `ARG NODE_TAG=22-bookworm-slim`; stage `base` (apt `ca-certificates` only per D9; `useradd` uid/gid 10001 `appuser`; WORKDIR `/app`) → stage `deps` (COPY `package.json package-lock.json` FIRST; `RUN --mount=type=cache,id=npm-cache,target=/root/.npm npm ci` — lock-exact, drift fails build; `chown -R 10001:10001 /app/node_modules` — vite writes dep-optimize cache as uid 10001) → leaf `dev` LAST (COPY tracked sources; `USER 10001`; `CMD ["npm","run","dev","--","--host","0.0.0.0","--strictPort"]`). Bare build yields `dev`. ▸ Verify: T5+T6 pass: `uv run pytest tests/dafi_sentinel/test_container_workflow.py -k "t5 or t6" -v`; drift drill: edit `package.json` without lockfile → deps build FAILS (revert, never commit drift); `NODE_TAG` drill: rebuild with `--build-arg NODE_TAG=22-alpine` rc 0 then restore default. ▸ Trace: R1 both scenarios; R2 both; R3 in-image half; R6 "Guards enforce with podman" partial. ▸ Est: +40 lines. ✅ GREEN 2 passed (~9s cached). GOTCHA: vite's TS-config loader writes bundled `.timestamp-*.mjs` NEXT TO the config ⇒ dev leaf adds `chown 10001:10001 /app` (dir only). GOTCHA 2: base stage made portable (apt/apk + useradd/adduser shim) — required for NODE_TAG drill. Drills: drift probe rc=1 fast (unresolvable dep E404; lock never regenerated — structural to `npm ci`); resolvable-drift variant revealed ≥14 min resolution latency instead of fast-fail (see risks; follow-up recommended, design mechanism kept per no-silent-deviation rule); NODE_TAG=22-alpine rc=0 (`added 221 packages`, musl set from lock) then default restored, drill image rmi'd. Full module post-GREEN: T5/T6/T7 pass; one T2 flake (in-image `test_inmemory_rlock` concurrent race, pre-existing, unrelated files) — green on immediate re-run + host-side 4/4.

## Phase 6 (Step 6, U2): Compose Finalize + Render Guard T8 (D6) — ~62 lines, RED→GREEN same commit

- [x] 6.1 **RED — extend** `test_container_workflow.py`: T8 `@requires_podman_compose` — plain `podman-compose … config` render lacks `web`; dual-profile render (`--profile api --profile web`) yields all THREE services with `web` publishing loopback-only `127.0.0.1:5173`, zero `volumes:` on web, `depends_on.api` present. ▸ Verify: FAILS (stub block incomplete/no ports). ▸ Est: +35 lines. ✅ Test `test_t8_compose_web_profile_gated_with_loopback_publish`; RED confirmed 1 failed (dual-profile render had only postgres+api, no web service existed).
- [x] 6.2 **GREEN — modify** `infra/podman/compose.yaml`: replace stub with final D6 `web` service (`profiles: ["web"]`, build per 4.1 outcome, `ports: ["127.0.0.1:5173:5173"]`, `environment: {DAFI_API_PROXY_TARGET: "http://api:8000"}`, `depends_on: {api: {condition: service_started}}`, `restart: unless-stopped`, NO volumes); update header comment with canonical dual-profile startup command. ▸ Verify: T8 passes; plain-up regression: `podman-compose -f infra/podman/compose.yaml up -d` starts ONLY postgres → `down -v`. ▸ Trace: R5 all three scenarios (chain start proven live in 8.1); R4 "Compose routes proxy to api" wiring. ▸ Est: +27 lines. ✅ GREEN T8 pass (exact 3-service render set asserted). Plain-up regression: exactly one container (`dafi-sentinel-postgres`), rc 0 up/down, zero residue after `-v`. Full module post-GREEN 9/9.

## Phase 7 (Step 7, U3): Freshness Guard T9 (D7) — ~40 lines

One work-unit commit (with Phase 8). ▸ Commit: `test(podman): add freshness and composed-boot e2e guards`

- [x] 7.1 **Extend** `test_container_workflow.py`: T9 `@requires_podman` — creation-time-vs-newest-input-mtime over `<project>_<service>` tags (`podman image inspect -f {{.Created}}` normalized to UTC vs newest mtime of `infra/podman/Containerfile(.web)`, `frontend/package*.json`, `frontend/{index.html,vite.config.ts,tsconfig*.json}`, `frontend/src/**`); absent tag ⇒ tolerant pass; stale ⇒ FAIL naming tag + remedy `podman rmi <tag> && podman-compose … up -d --build`. Named constant for `<project>` derivation (podman-compose 1.6.0 precedence: basename of compose-file dir ⇒ `podman`) — CONFIRM live at apply, correct if needed. Optional falsifiable drill: two consecutive builds reproducing identical IDs ⇒ may tighten to strict equality; otherwise creation-time stands. ▸ Verify (RED→GREEN in-commit): staleness drill — touch one input newer than a freshly built/composed image → T9 FAILS with named tag; restore freshness (rebuild/rmi+up) → passes; absent-tag case passes podman-present without stack. ▸ Trace: R6 "Stale image fails freshness guard" + "Guards enforce with podman". ▸ Est: +40 lines. ✅ `<project>` CONFIRMED LIVE: dual-profile build tagged `localhost/podman_api`+`localhost/podman_web` ⇒ `podman` = basename of `infra/podman/` (constant `COMPOSED_IMAGE_TAGS`). RED: 3 failed (`NameError` on helpers) + gate-off E2E skip, module intact. Comparison uses `{{.Created.Unix}}` (Go epoch integer = UTC-normalized; raw `.Created` is Go String() format, NOT RFC3339 — design assumption corrected). Staleness drill: post-`git pull` tree had inputs newer than images → T9 FAILED naming both tags; units pin `_select_stale` semantics (stale flagged / fresh tie tolerated / absent tolerated). DRILL FINDING: plain `podman rmi <tag>` only untags — T5/T1's `:local` guard tags pin identical content, so a fully-cached rebuild resurrects the old object with its original stale Created (proven twice live); remedy corrected to `podman rmi -f <tags> && … up -d --build`, hard-delete then produced new IDs with Created > input mtimes (1787541708/1787541733 > 1787540447) → GREEN. Absent-tag case: both tags removed → T9 PASSES podman-present sans stack.

## Phase 8 (Step 8, U3): Env-Gated Composed-Boot E2E (D8) — ~50 lines

- [x] 8.1 **Add** E2E test to same module: `skipif(os.environ.get("DAFI_COMPOSED_E2E") != "1")` + `@requires_podman_compose` (mirrors `DAFI_PGVECTOR_SMOKE` gating); unique project `-p dafi-composed-e2e-{os.getpid()}`; flow: dual-profile `up -d` → poll with `urllib` (no new deps): `:8000/docs` 200; `:5173` 200 with `id="root"` HTML; proxied `:5173/sessions` returns api-shaped response (401 accepted — FastAPI answered through proxy; 502/504/refused fails); whole body in `try/finally: down -v -p <name>`; `E2E_TIMEOUT = 600`. ▸ Verify (RED→GREEN in-commit): default suite skips E2E keeping it infra-free (`uv run pytest` exit 0); gated live run `DAFI_COMPOSED_E2E=1 uv run pytest tests/dafi_sentinel/test_container_workflow.py -k e2e -v` proves chain (precondition: ports 8000/5173 free — verified free pre-run) AND teardown leaves zero `-p` containers/networks (`podman ps -a --filter name=dafi-composed-e2e` + `podman network ls` clean). ▸ Trace: R7 all three scenarios; R4 "Compose routes proxy to api" end-to-end; R5 "Web implies api chain". ▸ Est: +50 lines. ✅ Gate verified both ways: default suite skips (`DAFI_COMPOSED_E2E != 1`, full suite exit 0, 278 passed/2 skipped/5 xpassed) + gated live run PASSED in 29.7s. APPLY-TIME CORRECTION to D8 expectation: unauthenticated GET /sessions returns **405** `{"detail":"Method Not Allowed"}` from the POST-only login route (verified against app factory via TestClient BEFORE the live run; no auth middleware intercepts GET) — acceptance set is {200,401,405}; proxy failures (502/504/refused/reset) retry to deadline and fail. Poller retries raw ConnectionResetError too (first live attempt leaked Errno 104 from read()-after-connect; broadened except to OSError/http.client.HTTPException). In-test residue assert after `down -v` (only on primary success, so teardown never masks a real failure); explicit post-run check: zero containers/networks matching `dafi-composed-e2e`. E2E builds its OWN `-p`-prefixed images (`dafi-composed-e2e-<pid>_{api,web}`), leaving T9's `<project>_*` tags untouched — clean isolation.

## Phase 9 (Step 9, U4): README Podman-First + Final Validation (R8, D10 warning) — ~55 lines

One work-unit commit. ▸ Commit: `docs(readme): make frontend workflows rootless-podman-first` ▸ Unit rollback: revert commit.

- [x] 9.1 **Rewrite** README frontend sections: "Run the dashboard" leads with the EXACT canonical command `podman-compose -f infra/podman/compose.yaml --profile api --profile web up -d` → `http://127.0.0.1:5173`; proxy env contract (`DAFI_API_PROXY_TARGET`, default + compose value); `DAFI_COMPOSED_E2E=1` gate doc with port-free precondition; shadow-artifact WARNING listing the same six patterns with the `rm -f` command (D10); demote host-Node workflow to fallback; refresh container-workflow reference rows (web port/image/env). ▸ Verify: execute README commands top-to-bottom from clean state (copy-paste fidelity). ▸ Trace: R8 "Docs cover the dashboard chain". ▸ Est: ~±55 lines.
- [x] 9.2 **Final validation**: `uv run pytest` (default, podman-less: green, new guards skip with reasons, exit 0 — R6 "Skips without podman"); enforce-mode `uv run pytest tests/dafi_sentinel/test_container_workflow.py -v` with podman (T5–T9 + E2E-skip all pass); plain-up postgres-only regression (R5 "Plain startup unchanged"); one live HMR check (D5): dual-profile up → open `http://127.0.0.1:5173`, confirm WS upgrade/HMR fires (browser or `curl` upgrade probe) → down -v; slice diff audit: every PR ≤ 400 lines. ▸ Trace: consolidated evidence R1–R8. ▸ Rollback boundaries: per-unit `git revert`; whole-change: delete `Containerfile.web` + `frontend/.containerignore` + new guard/E2E blocks, revert compose/vite/README hunks.

## Review Workload Forecast (end-of-artifact summary)

| Slice | PR | Contents | Est. lines | Own verification |
|-------|----|----------|-----------|------------------|
| U1 | PR-B1 | vite proxy (+4) · T7 RED (+18) · `.containerignore` (+12) · probe (0) | ~34 | T7 podman-less + probe rc 0 |
| U2 | PR-B2 | T5/T6 RED (+35) · `Containerfile.web` (+40) · T8 RED (+35) · compose (+27) | ~137 | T5/T6/T8 + drift/NODE_TAG drills + plain-up |
| U3 | PR-B3 | T9 (+40) · E2E (+50) | ~90 | staleness drill + gated live E2E + teardown |
| U4 | PR-B4 | README (~±55) | ~55 | README top-to-bottom + 9.2 validation |

```text
Total estimated lines: ~365 (all slices ≤ ~140; 400-line budget risk: Low)
Chained PRs recommended: Yes
Decision needed before apply: No
```

## Traceability Matrix

| Req (scenarios) | Tasks |
|---|---|
| R1 (2) | 5.1, 5.2 (NODE_TAG drill), 9.2 |
| R2 (2) | 5.2 (npm ci + drift drill), 5.1 (T6) |
| R3 (3) | 3.1, 3.2 (static), 5.2 (in-image build), 1.1 (parity), 7.1 (src freshness inputs) |
| R4 (2) | 2.1 (host default), 6.2 (compose wiring), 8.1 (proxied route) |
| R5 (3) | 6.1, 6.2, 8.1 (chain), 9.2 (plain-up regression) |
| R6 (3) | 3.1 (every-host T7), 5.1/6.1/7.1 (skipif reuse), 9.2 (skip-path + enforce-mode), 7.1 (stale fail) |
| R7 (3) | 8.1 (gate-off skip, gated proof, try/finally teardown) |
| R8 (1) | 9.1 |
