# Delta for containerized-backend-workflow

## ADDED Requirements

### Requirement: Web Dev Image Build Targets

`Containerfile.web` MUST build a multi-stage dev-server-only node image from `ARG NODE_TAG` (default `22-bookworm-slim`); its `dev` leaf MUST serve vite with HMR as non-root uid 10001.

#### Scenario: Default build serves dashboard

- WHEN the web image builds with default targets
- THEN vite serves with HMR as uid 10001

#### Scenario: Node tag overridable

- WHEN NODE_TAG is overridden
- THEN the base image uses that tag

### Requirement: Lock-Exact Frontend Dependency Sync

Dependency stages MUST run `npm ci` honoring package-lock.json exactly; manifest/lock drift MUST fail the build; node_modules MUST be baked in; an npm-cache mount SHOULD speed rebuilds.

#### Scenario: Consistent manifests install reproducibly

- GIVEN package.json matches package-lock.json
- WHEN the deps stage builds
- THEN installed versions match the lock exactly

#### Scenario: Lock drift fails build

- GIVEN a manifest edit missing from the lockfile
- WHEN the deps stage builds
- THEN the build fails without regenerating it

### Requirement: Frontend Context Excludes Host Artifacts

The web image MUST build from a dedicated frontend context denied by `frontend/.containerignore` (`node_modules/`, build output, emitted configs); only tracked sources enter layers. The repo-root context MUST NOT be used (its ignorefile denies `frontend/`).

#### Scenario: Host node_modules never leaks

- GIVEN host node_modules inside frontend/
- WHEN the web image builds
- THEN none of it reaches any layer

#### Scenario: Tracked configs beat emitted artifacts

- GIVEN gitignored emitted `.js` configs on host
- WHEN the web image builds
- THEN only tracked TypeScript configs enter the image

#### Scenario: Cleanup restores host parity

- GIVEN emitted `.js` shadowing tracked `.ts` edits
- WHEN verification touches vite.config.ts
- THEN artifacts are deleted first so host runs match container

### Requirement: Env-Configurable Dev Proxy Target

The dev proxy MUST read one env var `DAFI_API_PROXY_TARGET` (default `http://127.0.0.1:8000`) across all six API prefixes; compose MUST set it to the api service DNS name.

#### Scenario: Unset var keeps host behavior

- GIVEN DAFI_API_PROXY_TARGET unset
- WHEN vite starts on host
- THEN all prefixes target http://127.0.0.1:8000

#### Scenario: Compose routes proxy to api

- GIVEN compose sets DAFI_API_PROXY_TARGET=http://api:8000
- WHEN a proxied route hits 127.0.0.1:5173
- THEN the response comes from the api container

### Requirement: Additive Profile-Gated Web Service

Plain `podman-compose up -d` MUST stay postgres-only. The `web` profile MUST publish only loopback `127.0.0.1:5173`, mount nothing, and depend on api started. Starting the dashboard chain requires invoking compose with both profiles (`--profile api --profile web`); podman-compose does not auto-enable depended-on services.

#### Scenario: Plain startup unchanged

- WHEN the stack starts profileless
- THEN only postgres runs

#### Scenario: Profile exposes loopback dashboard

- WHEN the web profile starts
- THEN the dashboard answers at 127.0.0.1:5173
- AND nothing publishes externally or privileged

#### Scenario: Web implies api chain

- WHEN the stack starts with `--profile api --profile web`
- THEN api and postgres start before web serves

### Requirement: Frontend Container Guards Are CI-Safe

Podman-dependent guards extending `test_container_workflow.py` (no new markers) MUST skip without podman; the static context-denylist guard MUST run on every host. With podman they MUST verify web build, uid 10001, infra-free in-image vitest, context contents, and image freshness by comparing each composed `<project>_<service>` image's creation time against the newest mtime among its inputs (Containerfiles, package manifests and lockfiles, frontend configs, `frontend/src/**`), failing with the stale tag named and an `rmi`-rebuild remedy.

#### Scenario: Skips without podman

- GIVEN podman absent from PATH
- WHEN the guard module runs
- THEN frontend guards skip with reasons; session exits 0

#### Scenario: Guards enforce with podman

- GIVEN podman available
- WHEN the guards execute
- THEN build, uid, suite, context, and freshness checks pass

#### Scenario: Stale image fails freshness guard

- GIVEN a run reused an outdated `<project>_api`/`<project>_web` tag
- WHEN the freshness comparison executes
- THEN it fails naming the stale image and rmi remedy

### Requirement: Env-Gated Composed-Boot E2E

A composed-boot E2E MUST gate on `DAFI_COMPOSED_E2E=1`, use a unique compose project name, assert :8000/docs plus :5173 HTML and one proxied route, then tear down created resources.

#### Scenario: Gated off by default

- GIVEN DAFI_COMPOSED_E2E unset
- WHEN the default suite runs
- THEN the E2E skips, keeping the suite infra-free

#### Scenario: Gate proves api-to-web chain

- GIVEN DAFI_COMPOSED_E2E=1 and podman-compose available
- WHEN the E2E executes
- THEN :8000/docs, :5173 HTML, and a proxied route respond

#### Scenario: Teardown leaves no residue

- WHEN the E2E ends, pass or fail
- THEN its containers and networks are removed

### Requirement: Podman-First Frontend Documentation

README MUST make frontend workflows rootless-Podman-first (profile-gated startup, proxy env contract, E2E gate), demoting host-Node steps to fallback.

#### Scenario: Docs cover the dashboard chain

- GIVEN a contributor follows README "Run the dashboard"
- WHEN they copy the commands
- THEN `podman-compose -f infra/podman/compose.yaml --profile api --profile web up -d` serves 127.0.0.1:5173
