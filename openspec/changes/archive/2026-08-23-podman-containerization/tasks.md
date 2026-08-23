# Tasks: Podman Containerization of Backend Dev/Test/Run (PR-A)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~340 total: U1 ≈90, U2 ≈100, U3 ≈90, U4 ≈60 (incl. SDD docs) |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes (forced: FORCE-CHAINED delivery; each unit ≤ ~100 lines) |
| Suggested split | PR1=U1 → PR2=U2 → PR3=U3 → PR4=U4 (serialized slices) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low
```

Decision needed before apply: **Yes** — not for chain strategy (fixed: stacked-to-main); the HDFS-demo dirty-tree disposition (Task 0.1) gates U4 because it overlaps `README.md`.

### Suggested Work Units

| Unit | Goal | Likely PR | Base / notes |
|------|------|-----------|--------------|
| 0 | Pre-apply gate + branch | — | Gate: no overlapping dirty paths |
| 1 | Containerfile + .containerignore | PR 1 | `podman-containerization/pr-a` @ `main@3c26d5d` |
| 2 | compose `api` + wait helper | PR 2 | Builds on U1 (adds `/opt/dafi` COPY) |
| 3 | Guard tests T0–T3 | PR 3 | Verifies U1+U2; own slice per D8 |
| 4 | README Podman rewrite | PR 4 | Blocked until Task 0 resolved |

Publishing: each unit commits on `podman-containerization/pr-a`; open its PR via **GitHub MCP only** (never local push), base `main`. One open slice PR at a time; after PR N merges, continue on the branch so PR N+1's diff shows only unit N+1. Every PR carries the chained-pr "Chain Context" section (position, base, budget, 📍 diagram).

### Traceability Key (spec: specs/containerized-backend-workflow/spec.md)

R1 Multi-Stage Targets · R2 Lock-Exact Sync · R3 Context Exclusions · R4 Profile-Gated API · R5 DB Readiness Handoff · R6 In-Container Suite · R7 CI-Safe Guards · R8 Podman Docs

## Phase 0: Pre-Apply Gate & Branch Setup

- [x] 0.1 **Resolve HDFS-demo overlap**: land or stash the unrelated HDFS-demo slice — minimally its `README.md` hunks (user decision; ask if unclear). Apply REFUSES to start while `git status` reports changes under `README.md`, `infra/podman/**`, or `tests/dafi_sentinel/test_container_workflow.py`. ▸ Verify: `git status --porcelain | grep -E '^( M|\?\?)' | grep -E 'README\.md|infra/podman|test_container_workflow'` → empty. ▸ Trace: gate for R8 (U4); proposal AC "branch starts from clean HEAD". ▸ Rollback: none needed (no mutation).
- [x] 0.2 **Create branch** `podman-containerization/pr-a` from `main@3c26d5d`; publish ref via GitHub MCP. *(Apply ran local-only per orchestrator rule: no push; ref publication deferred to orchestrator post-review.)* ▸ Verify: remote branch HEAD == `3c26d5d`. ▸ Rollback: delete remote branch. ▸ Commit: none.

## Phase 1 (U1): Containerfile + Build Context (~90 lines)

One work-unit commit. ▸ Commit: `feat(podman): add multi-stage containerfile with runtime/test targets` ▸ Unit rollback: revert this commit; deletes only the two new files.

- [x] 1.1 **Create** `infra/podman/.containerignore`: denylist `.git/`, `**/.venv/`, `.local/`, `**/__pycache__/`, `.pytest_cache/`, `node_modules/`, `frontend/`, `scripts/`, `openspec/`, `PORTFOLIO.md`. ▸ Verify: `grep -F '**/.venv/' infra/podman/.containerignore`. ▸ Trace: R3 (denylist scenario). ▸ Result: shipped as repo-root `.containerignore` real file (commit 576a504) — evidence-based DEVIATION vs design File Changes table: podman-build(1) reads `.containerignore` from the CONTEXT directory (context = repo root here), so `infra/podman/.containerignore` was never read; root symlink replaced by real file, dead copy deleted.
- [x] 1.2 **Create** `infra/podman/Containerfile` per D1–D3, NO `/opt/dafi` COPY yet: `ARG PYTHON_TAG=3.13-slim-bookworm`; `base` (apt ca-certificates only, `ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1`, `WORKDIR /app`, `useradd -u 10001`); `COPY --from=ghcr.io/astral-sh/uv:<digest>` (capture digest from `uv:0.11` tag at apply); `deps-prod` (`uv sync --frozen --no-dev --no-install-project`); `deps-full` (`uv sync --frozen --no-install-project`); leaf `test` (`COPY pyproject.toml uv.lock dafi_sentinel tests` → `uv sync --frozen`, `USER 10001`, `CMD ["pytest","-q"]`); leaf `runtime` LAST (`COPY dafi_sentinel` → `uv sync --frozen --no-dev`, `USER 10001`, `CMD uvicorn dafi_sentinel.api.app:default_workbench_app --host 0.0.0.0 --port 8000`); cache mount `id=uv-cache,target=/root/.cache/uv` on sync RUNs. ▸ Verify: `podman build --target runtime -t dafi-sentinel-api:local .` rc 0; `podman image inspect -f '{{.Config.User}}' dafi-sentinel-api:local` → `10001`; `podman build --target test -t dafi-sentinel-test:local .` rc 0; drift drill: edit pyproject without lock → build FAILS (revert edit, never commit drift). ▸ Trace: R1 both scenarios; R2 both; R3 partial (context honored). ▸ Result: both targets build rc 0 via `podman build -f infra/podman/Containerfile --target … .` (literal task command needed `-f`: Containerfile lives outside the context root — deviation recorded); `Config.User`=10001 on both leaves; sizes api 653 MB / test 666 MB; uv pin digest `sha256:77280f2f…babf2eb7` = uv 0.11.33; drift drill: requirement-level manifest edit fails build rc 1 under `--locked` (comment-only edits pass by uv semantics); host `.venv` provenance absent from image (`pyvenv.cfg` points to `/usr/local/bin`, not `/home/dafi`).

## Phase 2 (U2): Compose API + Readiness Handoff (~100 lines)

One work-unit commit. ▸ Commit: `feat(podman): add profile-gated api service with db readiness handoff` ▸ Unit rollback: revert commit; restores postgres-only compose + removes script/COPY line.

- [x] 2.1 **Create** `infra/podman/scripts/wait_for_postgres.py`: read `DAFI_PGVECTOR_DSN`; poll psycopg `SELECT 1` (1 s interval, `WAIT_TIMEOUT` default 60); stderr progress; exit 1 with diagnostics on timeout; else `os.execvp(sys.argv[1:])`. ▸ Verify: `python -m py_compile infra/podman/scripts/wait_for_postgres.py`; live probe vs started pgvector container exits into given command. ▸ Trace: R5 both scenarios (helper logic). ▸ Result: py_compile rc 0; live probe on compose network exec'd into command at pid 1 rc 0; missing-DSN and unreachable-DSN (`WAIT_TIMEOUT=3`) paths exit rc 1 with clean diagnostics; BUGFIX during live verify: psycopg3 `conn.execute(...).fetchone()` mis-call (AttributeError crash-loop) replaced with explicit cursor before commit.
- [x] 2.2 **Amend Containerfile**: add `COPY infra/podman/scripts/wait_for_postgres.py /opt/dafi/wait_for_postgres.py` (both leaves inherit). Rebuild both targets. ▸ Verify: both target builds rc 0; `podman run --rm --entrypoint python dafi-sentinel-test:local /opt/dafi/wait_for_postgres.py --help` executes. ▸ Trace: R5 (baked-in helper clause). ▸ Result: COPY placed in shared `base` stage so both leaves inherit via one line; runtime + test rebuilt rc 0 post-fix (`podman build -f infra/podman/Containerfile --target … .`); script present root-owned 0644 at `/opt/dafi/` in both images, `Config.User`=10001 unchanged; `--help` invocation executes → clean rc 1 "DSN is not set" diagnostic (no traceback).
- [x] 2.3 **Extend** `infra/podman/compose.yaml` additively: `api` service — `profiles: ["api"]`; `build: {context: ../.., dockerfile: infra/podman/Containerfile, target: runtime}`; `ports: ["127.0.0.1:8000:8000"]`; `environment: DAFI_PGVECTOR_DSN=postgresql://sentinel:sentinel@postgres:5432/sentinel`; `depends_on: {postgres: {condition: service_healthy}}`; `entrypoint` → helper + uvicorn; `restart: unless-stopped`; **no volumes**. Postgres service untouched. ▸ Verify: `podman-compose -f infra/podman/compose.yaml config` rc 0 and api ABSENT without profile, PRESENT with `--profile api`; live: `podman-compose -f infra/podman/compose.yaml --profile api up -d` → `curl -fsS http://127.0.0.1:8000/docs` → `down -v`. ▸ Trace: R4 both; R3 (mounts-nothing scenario); R5 composed handoff. ▸ Result: config rc 0 both ways (api absent plain / present under profile); live: postgres healthy → wait-loop "ready; handing off" → uvicorn startup, container stable; curl `/docs` = HTTP 200 (root `/` = 404, auth-gated surface); `down -v` removed containers+volume+network cleanly. GOTCHA recorded: podman-compose tags its own `<project>_api` image and REUSES it on later ups — stale after manual rebuilds; fixed by `rmi` of the stale tag to force fresh compose build (crash-loop round 2 was stale-image, not code).

## Phase 3 (U3): Guard Tests (~90 lines)

One work-unit commit. ▸ Commit: `test(podman): add ci-safe container workflow guards t0-t3` ▸ Unit rollback: revert commit; deletes only the guard file.

- [x] 3.1 **Create** `tests/dafi_sentinel/test_container_workflow.py`: T0 always-on — parse `.containerignore`, assert `**/.venv/` + `.git/` denied (no podman needed); T1/T2/T3 gated by `pytest.mark.skipif(shutil.which("podman") is None, reason="podman not available")` — T1 runtime build rc 0 + `Config.User == "10001"`; T2 test-target build + `podman run --rm` suite rc == 0 (catches exit-5 drift); T3 `podman-compose -f infra/podman/compose.yaml config` rc 0. Subprocess: `timeout=900` builds / `300` runs, `capture_output=True`. NO new markers (`--strict-markers`). `test_pr1_no_external_infra.py` untouched. ▸ Trace: R7 both scenarios; R6 (suite-in-image assertion); R1/R2 enforcement. ▸ Result: shipped as 4 guards (commit 83f7cf1), all pass with podman. T0 hardened beyond literal task text: host checkout missing the denylist FAILS, in-image (no build context) skips honestly. T3 strengthened with rendered-content assertions (postgres present plain / api only under profile). ▸ DEVIATION (forced by guard evidence): `test_pr1_no_external_infra.py` inventory scoped to full checkouts (+12 lines incl. pytest import) — its present-paths list includes `frontend/`, which the test image deliberately omits and the build context denies, so R6 ("suite passes in-container") required the hunk; host enforcement unchanged (.git always present there).
- [x] 3.2 **Run guards**: `pytest tests/dafi_sentinel/test_container_workflow.py -v` → T0 passes everywhere, T1–T3 pass with podman; skip-path: rerun with podman scrubbed from PATH → skips with reasons, exit 0; regression: `pytest tests/dafi_sentinel/test_pr1_no_external_infra.py -q` exit 0. ▸ Trace: R7 skip/enforce scenarios. ▸ Result: enforce-mode 4 passed (T2 rebuilt both targets via `-f` form; full in-image suite rc 0 = 238 passed + honest skips); skip-path (env -i, podman-less PATH): 1 passed + 3 skipped with reasons, exit 0; pr1 regression exit 0; full host suite 243 passed / 1 skipped / 5 xpassed, exit 0 — default suite stays infra-free without podman services.

## Phase 4 (U4): README Rewrite (~60 lines) — GATED ON TASK 0.1

One work-unit commit. ▸ Commit: `docs(readme): rewrite backend workflows as rootless podman commands` ▸ Unit rollback: revert commit.

- [x] 4.1 **Rewrite** README backend sections: build/run/test flows as copyable rootless Podman commands (D5 command set verbatim, incl. in-network smoke with `DAFI_PGVECTOR_SMOKE=1` + in-network DSN); composed `--profile api` flow + `curl http://127.0.0.1:8000/docs` check; port-safety (>1024, loopback publish); SELinux guidance — `:Z` for the optional ro bind mount + named volume at `/app/.venv`, warn against host `.venv` mounts. ▸ Verify: execute README commands top-to-bottom from clean state. ▸ Trace: R8 (all workflows + port/SELinux clauses). ▸ Result: shipped as commit 308acbc (README +79/−25). NOTE — executed INLINE by orchestrator after two dead sub-agent attempts on this unit (delegation blocker documented). Spot-verified live: compose config renders rc 0; both images present; exact documented command `podman run --rm dafi-sentinel-test:local pytest tests/dafi_sentinel/test_orchestration.py -q` → 12 passed. Added container-workflow reference table (ports/.venv prohibition/:Z/env contract/compose tag gotcha); frontend left host-based pending PR-B; production-posture block kept as factory-semantics doc with container env note. Full-slice diff now 454+/25− = 479 lines > 400 single-PR budget → publish-time split decided: PR-A1 (3c26d5d..cbc863d, infra ~201 lines) ← main, PR-A2 (cbc863d..308acbc, guards+docs ~278 lines) ← PR-A1 branch, both ≤400.

## Phase 5: Final Validation & Slice Closure

- [x] 5.1 **Full in-container suite + guards**: `podman build --target test -t dafi-sentinel-test:local . && podman run --rm dafi-sentinel-test:local && pytest tests/dafi_sentinel/test_container_workflow.py -v`; plain-up regression: `podman-compose -f infra/podman/compose.yaml up -d` starts ONLY postgres → `down -v`. Confirm acceptance criteria (proposal §AC): targets build rootless, no host `.venv` baked/mounted, suite green in-image, profile-gated api on loopback, diff ≤400/unit. ▸ Trace: consolidated evidence R1–R7. ▸ Result (executed inline by orchestrator, `-f` build form): fresh test-target rebuild rc 0; full in-container suite **238 passed / 6 skipped / 5 xpassed** exit 0; guards T0–T3 **4/4 PASSED** (46s); plain-up regression started ONLY postgres (healthy, loopback 55432) → `down -v` clean. Acceptance criteria met except diff-per-unit clause reinterpreted as publish-time split PR-A1 (~201 lines) / PR-A2 (~278 lines) both ≤400.
- [x] 5.2 **Slice hygiene**: each merged/open PR diff shows ONLY its unit (retarget/rebase if polluted); Chain Context present in every PR body. ▸ Rollback boundaries: per-unit `git revert`; whole-change: delete new files + revert compose/README hunks. ▸ Result: published as 4 stacked PRs #4→#7, all MERGED into main @ `da3ac87` after progressive retarget to main; each PR diff = exactly its unit (201/174/348/283 lines ≤400); Chain Context + 📍 dependency diagram in every body; remote feature branches deleted post-merge.

## Traceability Matrix

| Req (scenarios) | Tasks |
|---|---|
| R1 (2) | 1.2, 3.1, 3.2, 5.1 |
| R2 (2) | 1.2 (drift drill), 3.1, 5.1 |
| R3 (2) | 1.1, 2.3, 5.1 (no-.venv-mounted) |
| R4 (2) | 2.3, 5.1 (plain-up regression) |
| R5 (2) | 2.1, 2.2, 2.3 |
| R6 (3) | 3.1 (T2), 5.1 (full suite + smoke stays gated); smoke in-network covered by 4.1 docs (D5, env-only, no code change) |
| R7 (2) | 3.1, 3.2 |
| R8 (1) | 4.1 (gated by 0.1) |

## Remediation Batch (pre-publication, post fresh-context 4-lens review)

Fresh adversarial review of `git diff 3c26d5d..308acbc` (risk PASS; reliability FAIL; readability FAIL; resilience pending on final state). Fixes executed INLINE by orchestrator after the fix-batch sub-agent died empty twice (delegation blocker documented):

- [x] F1 [CRITICAL] `wait_for_postgres.py` had zero automated coverage → `tests/dafi_sentinel/test_wait_for_postgres.py` (6 unit tests, monkeypatched psycopg/clock/execvp, no container needed). In-image runs resolve to the baked `/opt/dafi/wait_for_postgres.py` (repo path absent in-image — caught by T2 RED, fixed with baked-copy fallback).
- [x] F2 [HIGH] T3 now asserts loopback-only publishes and no host `.venv` mounts in rendered compose config.
- [x] F3 [HIGH] New T4 guard: bare `podman build` (no `--target`) must yield the runtime leaf (User 10001 + uvicorn CMD), temp tag cleaned up.
- [x] F4 [MED] `pyyaml>=6.0.1` declared explicitly in dev group (guard imports it; was only transitive); `uv lock` + `uv sync` updated.
- [x] F5 [HIGH] README + spec R2 said `uv sync --frozen`; shipped Containerfile uses `--locked` (`--frozen` does not fail on manifest/lock drift — Part A drift drill evidence). Spec wording corrected; correction note appended to design D2.
- [x] F6 [HIGH] README quick start now builds `dafi-sentinel-api:local` before referencing it (copy-paste works top-to-bottom).
- [x] F7 [MED/LOW batch] argv check moved before polling in wait script (covered by unit test); compose header comments unified to `podman-compose`; README rebuild-gotcha gives concrete discovery command; dev-password hint points at compose `environment:` block; Containerfile redundant-COPY comment corrected.
- [x] F8 [MED security doc] compose api service documents commented `DAFI_DEV_PASSWORD` env to keep generated credentials out of persistent container logs.

▸ Commits: `018fca7` test(podman): cover readiness handoff and harden container guards · `9053e0b` docs(podman): correct lock-sync flag, api build step, and compose guidance
▸ Evidence: guards+unit 11/11 PASSED · full host suite **250 passed / 1 skipped / 5 xpassed** exit 0 · T2 re-proved suite green in-image against rebuilt target.

## Publication split (recomputed after remediation)

Total diff vs main ≈ 970 lines incl. SDD artifacts → three stacked slices, each ≤400:
1. **PR-A1 infra** (`3c26d5d..cbc863d`): Containerfile, ignorefile, compose api, wait script (~201 lines)
2. **PR-A2 tests** (`cbc863d..018fca7`): guards T0–T4, readiness unit tests, pr1 scoping, pyyaml (~405 lines — verify exact count at split)
3. **PR-A3 docs+SDD** (`018fca7..HEAD`): README Podman-first, spec/design corrections, SDD artifacts (~300 lines)
