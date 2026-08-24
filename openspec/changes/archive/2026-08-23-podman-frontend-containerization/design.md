# Design: Podman Containerization of Frontend Dev Workflow (PR-B)

## Technical Approach

Extend the PR-A stack additively: a multi-stage `Containerfile.web` builds a dev-only vite image (`base → deps → dev`, leaf last) from a dedicated `frontend` context; compose grows a profile-gated `web` service publishing loopback `127.0.0.1:5173`; `vite.config.ts` reads one proxy env var with a host-preserving default; guards T5–T9 extend `test_container_workflow.py`; an env-gated composed-boot E2E automates PR-A carry-over #1 and an image-freshness guard automates carry-over #2. No frontend features touched, no prod stage, `package.json`/lock untouched (zero new deps).

## Architecture Decisions

### D1 — Web image identity, stage graph, pins
Options: tag `dafi-sentinel-web:local` vs `:dev` suffix vs repo-root context. **Chosen:** tag `dafi-sentinel-web:local`, single `dev` target declared LAST (bare build yields it, mirroring PR-A D1/D4); stages `base → deps → dev`; `ARG NODE_TAG=22-bookworm-slim` (matches local v22.23.1; vite 5.4.21 needs ^18||>=20). Rejected: `:dev` tag split (no consumer); root context (its ignorefile denies `frontend/` — empty COPY trap).

### D2 — Dedicated build context
**Chosen:** `context: ../../frontend` (compose) / explicit `podman build -f infra/podman/Containerfile.web … frontend` (guards, cwd repo root — podman reads ignorefiles from context root). New `frontend/.containerignore` denylist mirrors root `.gitignore` TS artifacts + `frontend/.gitignore`: `node_modules/ dist/ dist-ssr/ .vite/ coverage/ *.tsbuildinfo vite.config.js vite.config.d.ts vitest.config.js vitest.config.d.ts src/vite/*.js src/vite/*.d.ts .containerignore` (self-denial: a context-root ignorefile otherwise leaks into image layers; gains `Containerfile.web` if the D6 fallback triggers). Rejected: relaxing root ignorefile (weakens api context isolation).

### D3 — Deps stage: npm ci, cache mount, ownership
**Chosen:** manifests copied before source (PR-A D1 cache lesson); `RUN --mount=type=cache,id=npm-cache,target=/root/.npm npm ci` — **correction to exploration**: npm's default cache is `~/.npm` (not `/root/.cache/npm`); mounting the latter without `npm_config_cache` yields a useless cache. `npm ci` fails on manifest/lock drift (spec R2 analog of PR-A D2's corrected `--locked`). `chown -R 10001:10001 /app/node_modules` in deps stage: unlike PR-A D3's read-only `.venv`, vite dev **writes** its dep-optimize cache into `node_modules/.vite` as uid 10001. uid/gid 10001 `appuser` created in `base`, `USER 10001` only in leaf — mirrors PR-A D3.

### D4 — Proxy env contract
**Chosen:** `const API_TARGET = process.env.DAFI_API_PROXY_TARGET ?? "http://127.0.0.1:8000"` at top of `vite.config.ts`; all six prefixes reference it (explicit map, no loop magic). Follows the `csp-toggle.ts` `process.env` precedent (no `loadEnv`/`.env` files anywhere). Compose injects `DAFI_API_PROXY_TARGET: "http://api:8000"`. Unset ⇒ byte-identical host behavior (spec scenario). Rejected: `loadEnv` (new config surface), per-prefix vars (6-var sprawl).

### D5 — Dev-server flags & HMR over the published port
**Chosen:** container-only overrides in the leaf CMD: `CMD ["npm","run","dev","--","--host","0.0.0.0","--strictPort"]`. Vite's default bind is `localhost` — inside the container the published port would dead-end without `--host`; `--strictPort` prevents silent port drift breaking the `5173:5173` mapping. Config stays host-neutral (adding `host: true`/`strictPort` to `vite.config.ts` would alter host-run binding/fail-fast behavior for zero gain). HMR: browser at `http://127.0.0.1:5173` derives the WS URL from `window.location` (same-origin, same port) and the 1:1 publish forwards it — no `hmr`/`watch` config needed; `usePolling` pointless (fs baked, mounts forbidden). Verify live once at apply (browser or WS upgrade probe). Rejected: config-level host settings; `allowedHosts` tuning (IP access allowed by default in locked vite 5.4.21).

### D6 — Compose `web` service (additive, profile-gated)
```yaml
web:
  profiles: ["web"]
  build: {context: ../../frontend, dockerfile: ../infra/podman/Containerfile.web, target: dev}
  ports: ["127.0.0.1:5173:5173"]
  environment: {DAFI_API_PROXY_TARGET: "http://api:8000"}
  depends_on: {api: {condition: service_started}}
  restart: unless-stopped
```
**Profile invocation (FINDING 1, empirically fixed):** plain `up -d` stays postgres-only. podman-compose 1.6.0 does NOT auto-enable depended-on services gated behind another profile — `--profile web` alone renders `web` with no api/postgres and dies at boot (`KeyError: 'api'` in `check_dep_conditions`; verified live on podman 5.8.4 + podman-compose 1.6.0). ALL documented invocations standardize on BOTH profiles: `podman-compose -f infra/podman/compose.yaml --profile api --profile web up -d` (renders all three services correctly — verified). The compose header comment carries the same dual-profile command. `service_started` per spec — healthchecks contradict PR-A D4 spirit (readiness via baked helper, not compose support); api already self-gates on postgres readiness.

**Out-of-context `dockerfile:` (FINDING 4):** `../infra/podman/Containerfile.web` lives OUTSIDE the frontend context; 1.6.0 renders such paths verbatim but build-time resolution (context-relative vs CWD) is unproven — the probe crashed pre-build. MANDATORY EARLY apply-time verification before anything depends on it: stub `Containerfile.web` (two-line FROM) + compose `web` block → `podman-compose -f infra/podman/compose.yaml --profile api --profile web build web` MUST exit 0. On failure, pre-agreed fallback: move the file in-context (`frontend/Containerfile.web`, compose `dockerfile: Containerfile.web`) and add `Containerfile.web` to the D2 denylist — in-context resolution is definitionally safe. No volumes (source baked).

### D7 — Guards T5–T9 and freshness mechanism
Extend `tests/dafi_sentinel/test_container_workflow.py`; reuse module-level `requires_podman`/`requires_podman_compose` skipifs, `BUILD_TIMEOUT`/`RUN_TIMEOUT`; no new markers (`--strict-markers`):

| # | Gate | Assertion |
|---|---|---|
| T7 (static, every host — NO skipif, runs even podman-less) | none | `frontend/.containerignore` denies `node_modules/`, emitted configs, and itself (T0 analog; restores PR-A's every-host carve-out) |
| T5 | podman | build `frontend` context `--target dev -t dafi-sentinel-web:local` rc 0; `Config.User` == `10001` |
| T6 | podman | `podman run --rm dafi-sentinel-web:local npm run test` rc 0 + `passed` in stdout (T2 analog; vitest is infra-free) |
| T8 | podman-compose | render: plain config lacks `web`; dual-profile (`--profile api --profile web`) render yields all three services with `web` publishing loopback-only `:5173`, zero volumes, `depends_on.api` |
| T9 | podman | freshness guard (below) |

**Freshness (carry-over #2) — resolution of "ID comparison":** literal image-ID equality between podman-compose's `<project>_<service>` tag and a guard-made fresh build is unattainable — buildah stamps `created` at build time, so independent builds of identical input produce different IDs (false failures forever). **Chosen:** creation-time comparison keyed on the same `<project>_<service>` naming: `podman image inspect -f {{.Created}}` per tag vs newest mtime across `infra/podman/Containerfile(.web)`, `frontend/package*.json`, `frontend/{index.html,vite.config.ts,tsconfig*.json}`, `frontend/src/**`. Tag predates newest input ⇒ FAIL naming the stale tag with remedy `podman rmi <tag> && podman-compose … up -d --build`. Absent tag ⇒ tolerant pass (never composed). `.Created` arrives RFC3339+offset — normalize to UTC before comparing against input mtimes taken as UTC; `git pull` bumps mtimes forward so fresh-built images read false-stale — acceptable, fails safe toward rebuild. Project-name derivation mirrors podman-compose 1.6.0 precedence (no `-p`, env unset ⇒ basename of compose-file dir ⇒ `podman`) as a named constant; apply-time live check confirms/corrects it. Back-to-back-build drill retained ONLY as falsifiable fallback for strict ID equality: if two consecutive builds provably reproduce IDs on cache, tighten T9 to strict equality — otherwise creation-time comparison stands. Rejected: raw ID==ID as default (unsound); wrapper auto-rmi (masks, doesn't enforce); `pull_policy: build` (unverified in 1.6.0).

### D8 — Env-gated composed-boot E2E (carry-over #1)
pytest test in the same file; `skipif(os.environ.get("DAFI_COMPOSED_E2E") != "1")` + `requires_podman_compose` (mirrors `DAFI_PGVECTOR_SMOKE` gating; default suite stays infra-free). Unique project: `-p dafi-composed-e2e-{os.getpid()}` (parallel-safe; isolates from any dev stack). Flow: `podman-compose -f infra/podman/compose.yaml -p <name> --profile api --profile web up -d` → poll with `urllib` (no new deps): `:8000/docs` 200; `:5173` 200 with `id="root"` HTML; proxied route `:5173/sessions` returns api-shaped response — 401 accepted (auth-gated surface, proves FastAPI answered through the proxy), 502/504/connection-refused fails. Whole body wrapped in `try/finally: down -v -p <name>` — teardown on pass, fail, or partial-up; `E2E_TIMEOUT = 600`. Documented precondition: host ports 8000/5173 free (unique project name cannot free ports).

### D9 — First-build native binaries
Lockfile pins `@esbuild/linux-x64@0.21.5` and `@rollup/rollup-linux-x64-gnu@4.62.2` as platform-optional deps; `npm ci` in-image installs the linux-x64 set; bookworm glibc satisfies their baselines. Expected apt footprint: `ca-certificates` only (registry.npmjs.org is HTTPS) — same as PR-A base. Proof is structural: T5 build + T6 in-image suite fail loudly on any binary mismatch; no separate mitigation task.

### D10 — Shadowing-artifact hygiene (HIGH gotcha)

Emitted gitignored artifacts shadow tracked sources on host runs in TWO places: root configs `frontend/vite.config.{js,d.ts}` / `vitest.config.{js,d.ts}` resolve before the tracked `.ts`, and `frontend/src/vite/csp-toggle.{js,d.ts}` shadow `csp-toggle.ts` because the test imports `"../vite/csp-toggle"` extensionless and Vite's resolver prefers `.js` over `.ts`. Both sets verified on disk today: THREE root files (`vitest.config.d.ts` never emitted) plus the two `src/vite` pairs. Explicit apply step: `rm -f` all six patterns before every host-side verification of `vite.config.ts` OR `src/vite/*` edits — never assume counts, `rm -f` tolerates absence (in-image runs immune; D2's ignorefile excludes every pattern). README carries the same warning listing the same set.

## Data Flow

```
Browser ──HTTP──> 127.0.0.1:5173 ══publish══> web (vite dev, uid 10001, baked src+node_modules)
   │                                              │ proxy /sessions /evidence /qa /charts /roles /audits
   │                                              │ target = $DAFI_API_PROXY_TARGET (http://api:8000)
   └──WS-HMR (same origin, same port)             ▼
                                              api (uvicorn :8000) ──DSN──> postgres (:5432, unmapped)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `infra/podman/Containerfile.web` | Create | 3-stage node image (D1–D3, D5), ~40 lines |
| `frontend/.containerignore` | Create | frontend-context denylist (D2), ~12 lines |
| `infra/podman/compose.yaml` | Modify (+~25) | additive `web` service + header comment (D6) |
| `frontend/vite.config.ts` | Modify (+~4) | env-configurable proxy target (D4) |
| `tests/dafi_sentinel/test_container_workflow.py` | Modify (+~160) | T5–T9 + gated E2E (D7/D8) |
| `README.md` | Modify (~55) | Podman-first dashboard/tests/reference rows + shadow-artifact warning (D10: root + `src/vite` sets) |
| `frontend/src/**`, `package.json`, `package-lock.json`, Python pkg | None | untouched |

## Interfaces / Contracts

| Contract | Value |
|---|---|
| Env | `DAFI_API_PROXY_TARGET` (default `http://127.0.0.1:8000`; compose sets `http://api:8000`); gates `DAFI_COMPOSED_E2E=1`; `NODE_TAG` build-arg |
| Images | `dafi-sentinel-web:local` (target `dev`); compose-owned `<project>_web`/`<project>_api` |
| Ports | web `127.0.0.1:5173:5173` loopback-only; existing mappings unchanged |
| Commands | canonical startup: `podman-compose -f infra/podman/compose.yaml --profile api --profile web up -d`; in-image: `npm run test` (vitest), leaf CMD vite; E2E `-p dafi-composed-e2e-<pid>` |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Static (any host, never skipped) | denylist contents incl. self-denial (T7) | file parse, T0 pattern |
| Integration (podman) | web build, uid, in-image vitest, dual-profile render, freshness (T5/T6/T8/T9) | subprocess guards, auto-skip |
| E2E (gated) | api→web chain + proxy + teardown | `DAFI_COMPOSED_E2E=1` pytest |

Strict TDD ordering: each guard lands red (feature missing) before its infra unit; `uv run pytest` stays green podman-less throughout; frontend vitest untouched (no UI change).

## Task-Ordering Hints

1. D10 artifact cleanup (`rm -f` six patterns: root config artifacts + `frontend/src/vite/*.{js,d.ts}`) → 2. `vite.config.ts` proxy (verify host default + vitest) → 3. T7 red/green (denylist incl. self-denial) → 4. **EARLY dockerfile-resolution probe (FINDING 4):** stub `Containerfile.web` + compose `web` block → dual-profile `podman-compose … build web` rc 0 before ANY dependent work; failure ⇒ D6 in-context fallback → 5. real `Containerfile.web` stages + T5/T6 red/green → 6. compose finalize + T8 (dual-profile render) → 7. T9 freshness (confirm live tag constant) → 8. E2E (dual-profile) → 9. README (incl. shadow-artifact warning). Split infra/guards/docs into force-chained slices only if >400 lines (forecast ~340–385: Low risk).

## Risks

| Risk | Sev | Mitigation |
|---|---|---|
| Stale `.js` shadows `.ts` edits on host | High | D10 deletion step + README warning |
| Compose tag-staleness replicates for `_web` | Med | T9 guard + remedy message |
| `<project>` name constant wrong | Low-Med | apply-time live confirm (D7); tolerant absent-tag pass |
| `--profile` repeat syntax / `-p` quirks in 1.6.0 | Low-Med | dual-profile invocation verified live; apply-time verify of D8 `-p` line before E2E logic |
| Out-of-context `dockerfile:` build resolution unverified | Med-High | MANDATORY early probe (hint #4) gates all dependent work; pre-agreed D6 fallback (in-context Containerfile) |
| HMR WS over publish | Low | D5 same-origin reasoning + one live check |
| Port collision during E2E | Low | documented precondition, env-gated manual run |

## Migration / Rollout

No migration. Additive/profile-gated: postgres-only default cannot regress. Rollback: delete `Containerfile.web` + `frontend/.containerignore` + new guard/E2E blocks; revert compose/vite/README hunks.

## Open Questions

None blocking. Apply-time verifications folded into tasks: out-of-context `dockerfile:` resolution probe FIRST (D6, pre-agreed fallback); live `<project>_web` tag constant (D7); `-p` behavior (D8); one live HMR check (D5); falsifiable back-to-back-ID drill to optionally tighten T9 to strict equality (D7).
