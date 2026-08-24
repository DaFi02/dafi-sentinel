# Exploration: podman-frontend-containerization (PR-B)

Change: `podman-frontend-containerization` · Explored: 2026-08-23 · Store: hybrid (this file + Engram obs `sdd/podman-frontend-containerization/explore`)
Scope guard: containerize the EXISTING frontend only — the frontend REDESIGN is explicitly deferred by the user.

## Current State

**Toolchain / Node version evidence**
- `frontend/package.json`: no `engines` field; React 18.3, Vite ^5.4.8, Vitest ^2.1.2, TS ^5.6.2, @types/node ^20.
- `frontend/package-lock.json`: lockfileVersion 3 (npm 8+); locked vite 5.4.21 (requires Node ^18 || >=20), typescript 5.9.3.
- No CI workflows exist (`​.github/workflows` absent) → nothing enforces a Node version today; local runtime is Node v22.23.1 / npm 10.9.8, podman 5.8.4, podman-compose 1.6.0.

**Dev proxy today**
- `frontend/vite.config.ts` (tracked source of truth): `server.port 5173`, proxy hardcodes `http://127.0.0.1:8000` for 6 prefixes (`/sessions /evidence /qa /charts /roles /audits`).
- `frontend/src/api/client.ts:110` — `BASE_URL = "/"`: ALL API calls are same-origin relative → fully proxy-dependent; no CORS surface (browser only ever talks to the published loopback port).
- Env precedent: `src/vite/csp-toggle.ts` reads `DAFI_DEV_NO_CSP_META` via `process.env`; no `loadEnv`/`import.meta.env` usage anywhere.

**Vitest setup**: jsdom + globals, `setupFiles ./src/test/setup.ts`, `forbidOnly`, `testTimeout 10000`, `css:false`. 7 test files under `src/test/`, fetch mocked, zero network → naturally infra-free like backend R6.

**Compose / infra surface PR-B extends**
- `infra/podman/compose.yaml`: default = postgres only (loopback :55432); profile-gated `api` (:8000, DSN via service DNS `postgres:5432`, readiness via baked `/opt/dafi/wait_for_postgres.py` exec, no volumes, built from repo-root context).
- `.containerignore` (repo root, OPERATIVE — podman reads ignorefile from context dir): denies `node_modules/`, `frontend/`, `scripts/`, etc.
- Guard pattern to extend: `tests/dafi_sentinel/test_container_workflow.py` T0–T4 with `skipif(shutil.which("podman"))`, BUILD_TIMEOUT 900 / RUN_TIMEOUT 300, no new markers (`--strict-markers`).

**Carry-overs confirmed** (`archive/2026-08-23-podman-containerization/verify-report.md`):
1. Composed-boot E2E automated test (currently manual-verified twice).
2. Stale-image freshness guard — root cause in tasks 2.3: podman-compose tags its own `<project>_api` and reuses it across ups after manual rebuilds; fix was manual `podman rmi`.

**README surface to update**: "Run the dashboard" (~L240–247) and "Run the slice tests" L263–264 ("Frontend (host-based until PR-B)") + container-workflow reference table.

## GOTCHA (found during exploration) [HIGH]

Gitignored emitted artifacts `frontend/vite.config.js`, `vitest.config.js` (+ `.d.ts`) exist locally (root `.gitignore` lists them as composite-project build outputs). Vite/Vitest resolve `.js` BEFORE `.ts`, so on host runs a stale artifact shadows edits to the tracked TS configs. In-container builds copy tracked sources only → immune. PR-B tasks must delete/rebuild these artifacts when touching `vite.config.ts`.

## Affected Areas

- `infra/podman/compose.yaml` — add profile-gated `web` service (loopback :5173)
- `infra/podman/Containerfile.web` (new) — multi-stage node image (deps + dev leaf)
- `frontend/.containerignore` (new) — denylist for the frontend context
- `frontend/vite.config.ts` — env-configurable proxy target
- `tests/dafi_sentinel/test_container_workflow.py` — new guards T5+
- `README.md` — frontend workflows become rootless-Podman-first
- `openspec/specs/containerized-backend-workflow/spec.md` — delta requirements

## Approaches

| Fork | Options | Recommendation | Effort |
|---|---|---|---|
| Web image context | (a) dedicated `../../frontend` context + `frontend/.containerignore`; (b) repo-root context relaxing root ignorefile | **(a)** — root ignore DENIES `frontend/`; repo-root context would COPY nothing; small isolated context mirrors PR-A deviation #1 lesson | Low |
| Node base image | (a) `node:22-bookworm-slim` (matches actual local v22.23.1); (b) `node:20-bookworm-slim` (matches @types/node ^20). Both satisfy vite 5 (^18\|\|>=20) | **(a)** with `ARG NODE_TAG`, digest-pin option following uv precedent | Low |
| Proxy env config | (a) single `DAFI_API_PROXY_TARGET` read via `process.env`, default `http://127.0.0.1:8000`; (b) loadEnv/.env files; (c) per-prefix map | **(a)** — one var covers all 6 prefixes; mirrors csp-toggle env precedent; compose sets `http://api:8000` | Low |
| web→api ordering | (a) `depends_on: api: service_started` (auto-pulls api+postgres under `--profile web`); (b) no depends_on (502s until api up); (c) add api healthcheck | **(a)** — (c) contradicts design D4 spirit ("readiness MUST NOT depend on compose healthcheck support") | Low |
| Vitest deps strategy | (a) baked `npm ci` + cache mount `id=npm-cache,target=/root/.cache/npm`; (b) bind-mounted host node_modules | **(a)** — lock-exact analog of `uv sync --locked` (R2 analog); avoids esbuild/@rollup linux-x64 native-binary mismatch; honors R3 "mounts nothing" | Low |
| Composed-boot E2E | (a) env-gated `DAFI_COMPOSED_E2E=1` pytest guard w/ unique `-p` project name + finally-teardown; (b) always-run skipif(podman-compose) guard | **(a)** — mirrors `DAFI_PGVECTOR_SMOKE` gating; keeps default suite fast/infra-free. Cover full chain: api+web profiles → curl :8000/docs AND :5173 HTML + proxied route | Medium |
| Stale-image freshness | (a) ID-comparison guard (`podman image inspect <project>_api` vs fresh-build ID, fail with rmi hint); (b) wrapper script automating pre-up rmi; (c) `pull_policy: build` experiment | **(a)** core assertion; (b) optional DX sugar; (c) podman-compose 1.6.0 support UNVERIFIED — treat as unknown | Medium |

## Recommendation

Composite of the recommended column: dedicated frontend-context `Containerfile.web` (deps stage `npm ci` + dev leaf, non-root uid 10001, `ARG NODE_TAG=22-bookworm-slim`), single-env-var proxy target, profile-gated `web` service publishing loopback :5173 with `depends_on api service_started`, guards extending the T0–T4 file, env-gated composed-boot E2E covering the api→web chain (folds carry-over #1 into an automated flow that also exercises the proxy), stale-image ID-comparison guard (carry-over #2), README Podman-first rewrite for frontend sections.

Estimated diff ~300–380 lines incl. SDD docs — fits the 400-line budget as one slice, or splits infra/guards/docs if it grows (force-chained stacked-to-main).

## Risks

1. [HIGH] Config-artifact shadowing: stale gitignored `vite.config.js`/`vitest.config.js` shadow tracked `.ts` edits on host runs (js resolves first) — changes can look dead locally while working in-container. Mitigation: delete/rebuild artifacts as an explicit task step.
2. [MEDIUM] Build-context trap: root `.containerignore` denies `frontend/`; naive repo-root context yields empty COPY. Must use dedicated frontend context.
3. [MEDIUM] podman-compose 1.6.0 tag reuse will replicate the `<project>_api` staleness gotcha for `<project>_web`; `pull_policy` support unverified.
4. [MEDIUM] Profile dependency pull-in: `--profile web up` auto-starts api AND postgres — must be spec'd explicitly so plain `up -d` stays postgres-only.
5. [LOW] HMR through published loopback port should work without extra ws config (browser connects directly to 127.0.0.1:5173) — verify live once.
6. [LOW] Native binaries (esbuild, @rollup) ship linux-x64 prebuilts — apt need expected limited to ca-certificates; verify first build.
7. [LOW] No engines field / no CI: container pin becomes the ONLY enforced Node runtime.

## Ready for Proposal

Yes. Open decisions to settle in proposal/design: final Node pin (rec 22-slim), dev-server-only scope confirmation (defer production static-serving target — rec defer), E2E gate var name, stale-guard mechanism choice, image/tag naming (`dafi-sentinel-web:local`).
