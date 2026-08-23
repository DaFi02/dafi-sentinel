# Delta for containerized-backend-workflow

## ADDED Requirements

### Requirement: Multi-Stage Image Build Targets

The backend MUST build two Containerfile targets: `runtime` (production deps only, non-root user 10001) and `test` (dev group included), with `runtime` last so a bare build yields the deployable image.

#### Scenario: Default build yields runtime

- WHEN the image builds without an explicit target
- THEN it contains production deps only
- AND runs as non-root user 10001

#### Scenario: Test target carries dev tooling

- WHEN the image builds targeting `test`
- THEN the dev-group toolchain installs and the suite runs in-image

### Requirement: Lock-Exact Dependency Sync

Dependency stages MUST install lock-exact (`uv sync --locked`); builds MUST fail instead of resolving when pyproject.toml and uv.lock disagree.

#### Scenario: Consistent manifests build reproducibly

- GIVEN pyproject.toml and uv.lock agree
- WHEN either target builds
- THEN installed versions match the lock exactly

#### Scenario: Lock drift fails build

- GIVEN a manifest edit absent from uv.lock
- WHEN any target builds
- THEN the build fails without regenerating the lockfile

### Requirement: Build Context Excludes Host Artifacts

A `.containerignore` denylist MUST exclude host artifacts (`.venv`, `.git/`, caches); host `.venv` MUST NEVER enter an image layer or mount.

#### Scenario: Denylist blocks virtualenv leakage

- GIVEN host `.venv` in context
- WHEN any image builds
- THEN no `.venv` content reaches the image

#### Scenario: Composed API mounts nothing

- WHEN the api service runs under compose
- THEN only baked-in source/deps are used
- AND no host `.venv` path mounts

### Requirement: Additive Profile-Gated Compose API Service

Plain `podman-compose up -d` MUST stay unchanged (postgres only); `api` MUST be profile opt-in publishing only on loopback `127.0.0.1:8000`, leaving postgres untouched.

#### Scenario: Plain startup unchanged

- WHEN the stack starts without a profile
- THEN only the postgres service runs

#### Scenario: Profile exposes API on loopback

- WHEN the stack starts with the api profile
- THEN api serves 127.0.0.1:8000 from the runtime image
- AND nothing publishes externally or privileged

### Requirement: Database Readiness Handoff

API containers MUST gate server start on a baked-in helper probing PostgreSQL via `DAFI_PGVECTOR_DSN`; readiness MUST NOT depend on compose healthcheck support.

#### Scenario: API waits for database

- GIVEN postgres still starting
- WHEN the api container launches
- THEN the helper polls until reachable, then execs the server

#### Scenario: Probe timeout fails visibly

- GIVEN an unreachable database
- WHEN the probe window expires
- THEN the api container exits nonzero with diagnostics

### Requirement: Containerized Test Execution Contract

The default suite MUST pass inside the `test` image with zero external services. The pgvector smoke MUST stay env-gated (`DAFI_PGVECTOR_SMOKE=1` plus in-network `DAFI_PGVECTOR_DSN`) without code changes.

#### Scenario: Infra-free suite passes in-container

- GIVEN test image built from tree
- WHEN the default suite runs in-container
- THEN gated-off tests pass with zero external services

#### Scenario: Smoke remains gated off

- GIVEN unset smoke vars
- WHEN the suite runs in-container
- THEN smoke skips, exit code 0

#### Scenario: In-network pgvector smoke

- GIVEN pgvector on a shared Podman network
- WHEN the image runs with smoke vars + in-network DSN
- THEN the live-adapter smoke passes

### Requirement: Guard Tests Are CI-Safe

Container guards MUST skip cleanly when podman is absent; the build-context guard MUST run on every host.

#### Scenario: Skips without podman

- GIVEN podman missing from PATH
- WHEN the guard module executes
- THEN podman-dependent guards skip with reasons
- AND session exits 0

#### Scenario: Guards enforce with podman

- GIVEN podman available
- WHEN the guards execute
- THEN both-target builds, user 10001, in-image suite pass, and compose rendering verify

### Requirement: Podman-First Documentation

README MUST document every backend workflow as rootless Podman commands with unprivileged ports and SELinux volume labels for mounts.

#### Scenario: Docs cover all workflows

- GIVEN a contributor following the README
- WHEN any backend workflow executes
- THEN steps are copyable rootless Podman commands
- AND port-safety and SELinux guidance accompany mounts
