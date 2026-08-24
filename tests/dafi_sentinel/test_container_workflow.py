"""CI-safe guards for the rootless Podman container workflow.

These tests assert the container contracts shipped by the
``podman-containerization`` change (specs containerized-backend-workflow,
design D7):

* T0 (always-on): the build-context denylist excludes host artifacts
  (``**/.venv/``, ``.git/``) so host virtualenvs never enter an image.
* T1: the ``runtime`` target builds and the image runs as uid 10001.
* T2: the ``test`` target builds and the default suite passes in-image
  (a nonzero exit, including pytest's exit-5 empty-collection code, fails).
* T3: the compose file renders, the api service is profile-gated
  (plain config stays postgres-only), every published port is
  loopback-only, and no host ``.venv`` path is mounted.
* T4: a bare ``podman build`` (no ``--target``) yields the deployable
  runtime leaf — uvicorn entrypoint running as uid 10001.
* T5: the web dev target builds from the dedicated frontend context and
  the image runs as uid 10001.
* T6: the web dev image runs the infra-free vitest suite in-image
  (a nonzero exit fails).
* T7 (always-on): the dedicated ``frontend`` build context denylist
  excludes host artifacts (``node_modules/``, build output, emitted
  config shadows) and itself, so only tracked sources enter web images.
* T9: each composed ``<project>_{api,web}`` image postdates the newest
  mtime among its inputs; stale tags fail naming an ``rmi``-rebuild
  remedy, absent tags tolerate (never composed).
* E2E (gated on ``DAFI_COMPOSED_E2E=1``): a unique-project compose boot
  serves :8000/docs, :5173 HTML, and a proxied route through the
  api->web chain, then tears everything down.

Podman-dependent guards skip cleanly when podman is absent so podman-less
CI stays green (exit 0). No new pytest markers are registered — the
project runs with ``--strict-markers`` — so only the built-in ``skipif``
mark is used. Builds pass ``-f infra/podman/Containerfile`` explicitly
because podman resolves ignorefiles from the context root, not from the
Containerfile directory.
"""

import http.client
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from time import monotonic, sleep

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTAINERFILE = "infra/podman/Containerfile"
CONTAINERFILE_WEB = "infra/podman/Containerfile.web"
API_IMAGE = "dafi-sentinel-api:local"
TEST_IMAGE = "dafi-sentinel-test:local"
WEB_IMAGE = "dafi-sentinel-web:local"

# Subprocess ceilings from design D7: builds are slow cold, suite runs are
# bounded well below CI job limits.
BUILD_TIMEOUT = 900
RUN_TIMEOUT = 300

# Composed-boot E2E gate (design D8): mirrors DAFI_PGVECTOR_SMOKE so the
# default suite stays infra-free; E2E_TIMEOUT bounds up/poll/teardown.
E2E_GATE_ENV = "DAFI_COMPOSED_E2E"
E2E_TIMEOUT = 600

# Compose project-name derivation mirrors podman-compose 1.6.0 precedence
# (no -p flag, COMPOSE_PROJECT_NAME unset): basename of the compose-file's
# directory. Confirmed live at apply time: the dual-profile build tagged
# localhost/podman_api and localhost/podman_web for infra/podman/compose.yaml.
COMPOSE_PROJECT = Path("infra/podman/compose.yaml").parent.name
COMPOSED_IMAGE_TAGS = (f"{COMPOSE_PROJECT}_api", f"{COMPOSE_PROJECT}_web")

requires_podman = pytest.mark.skipif(
    shutil.which("podman") is None, reason="podman not available"
)
requires_podman_compose = pytest.mark.skipif(
    shutil.which("podman-compose") is None, reason="podman-compose not available"
)


def _build_target(target: str, tag: str) -> subprocess.CompletedProcess[str]:
    """Build one Containerfile target from the repo-root context (-f form)."""
    return subprocess.run(
        [
            "podman",
            "build",
            "-f",
            CONTAINERFILE,
            "--target",
            target,
            "-t",
            tag,
            ".",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT,
        check=False,
    )


def _build_web(tag: str) -> subprocess.CompletedProcess[str]:
    """Build the web dev target from the dedicated frontend context (-f form).

    The context root carries ``frontend/.containerignore``; podman reads
    ignorefiles from the context root, not the Containerfile directory.
    """
    return subprocess.run(
        [
            "podman",
            "build",
            "-f",
            CONTAINERFILE_WEB,
            "--target",
            "dev",
            "-t",
            tag,
            "frontend",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT,
        check=False,
    )


def test_containerignore_denylist_blocks_host_venv_and_git():
    """T0: the denylist denies ``**/.venv/`` and ``.git/`` on every host."""
    ignore_path = PROJECT_ROOT / ".containerignore"
    if not ignore_path.exists():
        if (PROJECT_ROOT / ".git").exists():
            pytest.fail(".containerignore missing from the host build context")
        # In-image runs have no build context: the denylist itself keeps
        # .git/ out of images, so its co-absence marks containerized exec.
        pytest.skip("not a host build context (no .containerignore, no .git)")

    content = ignore_path.read_text(encoding="utf-8")
    patterns = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    # Host virtualenv and VCS metadata must never reach an image layer.
    assert "**/.venv/" in patterns
    assert ".git/" in patterns


def test_t7_frontend_containerignore_denylist_blocks_host_artifacts():
    """T7: the frontend context denylist denies host artifacts on every host.

    Always-on on every host (no skipif mark — runs podman-less, restoring
    the PR-A every-host carve-out). The dedicated ``frontend`` context must
    never ship host ``node_modules``, build output, emitted ``.js``/
    ``.d.ts`` config shadows (they resolve before the tracked ``.ts``
    sources), or the ignorefile itself (design D2 self-denial).
    """
    ignore_path = PROJECT_ROOT / "frontend" / ".containerignore"
    if not ignore_path.exists():
        if (PROJECT_ROOT / ".git").exists():
            pytest.fail(
                "frontend/.containerignore missing: the web build context "
                "would leak host node_modules and emitted config shadows "
                "into layers"
            )
        # In-image runs have no build context: the root denylist excludes
        # frontend/ and .git/, so their co-absence marks containerized exec.
        pytest.skip("not a host build context (no .git)")

    content = ignore_path.read_text(encoding="utf-8")
    patterns = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    denied = {
        # Host dependencies and build output.
        "node_modules/",
        "dist/",
        "dist-ssr/",
        ".vite/",
        "coverage/",
        "*.tsbuildinfo",
        # Emitted root configs that shadow the tracked .ts sources.
        "vite.config.js",
        "vite.config.d.ts",
        "vitest.config.js",
        "vitest.config.d.ts",
        # Emitted src/vite artifacts that shadow csp-toggle.ts resolution.
        "src/vite/*.js",
        "src/vite/*.d.ts",
        # Self-denial: a context-root ignorefile otherwise enters layers.
        ".containerignore",
    }
    missing = denied - patterns
    assert not missing, f"frontend/.containerignore misses denials: {sorted(missing)}"


@requires_podman
def test_runtime_target_builds_and_runs_as_uid_10001():
    """T1: the runtime target builds rc 0 and Config.User pins uid 10001."""
    build = _build_target("runtime", API_IMAGE)
    assert build.returncode == 0, build.stderr[-4000:]

    inspect = subprocess.run(
        ["podman", "image", "inspect", "-f", "{{.Config.User}}", API_IMAGE],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert inspect.returncode == 0, inspect.stderr
    assert inspect.stdout.strip() == "10001"


@requires_podman
def test_test_target_builds_and_suite_passes_in_image():
    """T2: the test target builds rc 0 and the in-image suite exits 0."""
    build = _build_target("test", TEST_IMAGE)
    assert build.returncode == 0, build.stderr[-4000:]

    run = subprocess.run(
        ["podman", "run", "--rm", TEST_IMAGE],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    # A green run must have executed tests; pytest exits 5 on empty collection.
    assert "passed" in run.stdout


@requires_podman
@requires_podman_compose
def test_compose_config_renders_with_profile_gated_api():
    """T3: compose config renders rc 0; api appears only under its profile."""
    plain = subprocess.run(
        ["podman-compose", "-f", "infra/podman/compose.yaml", "config"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    assert plain.returncode == 0, plain.stderr[-2000:]

    plain_services = yaml.safe_load(plain.stdout)["services"]
    assert "postgres" in plain_services  # render produced real content
    assert "api" not in plain_services  # plain startup unchanged (profile off)

    profiled = subprocess.run(
        [
            "podman-compose",
            "-f",
            "infra/podman/compose.yaml",
            "--profile",
            "api",
            "config",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    assert profiled.returncode == 0, profiled.stderr[-2000:]
    rendered = yaml.safe_load(profiled.stdout)["services"]
    assert "api" in rendered

    # Spec R4/R3 enforcement: loopback-only publish and no host .venv
    # mounts anywhere in the rendered stack.
    for service in rendered.values():
        for port in service.get("ports", []) or []:
            assert str(port).startswith("127.0.0.1:"), f"non-loopback publish: {port}"
        for volume in service.get("volumes", []) or []:
            source = str(volume.split(":")[0] if isinstance(volume, str) else volume.get("source", ""))
            assert ".venv" not in source, f"host .venv mounted: {volume}"


@requires_podman
def test_bare_build_defaults_to_runtime_leaf():
    """T4: `podman build` without --target yields the deployable runtime."""
    default_image = "dafi-sentinel-default:local"
    build = subprocess.run(
        ["podman", "build", "-f", CONTAINERFILE, "-t", default_image, "."],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT,
        check=False,
    )
    try:
        assert build.returncode == 0, build.stderr[-4000:]

        user = subprocess.run(
            ["podman", "image", "inspect", "-f", "{{.Config.User}}", default_image],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert user.returncode == 0, user.stderr
        assert user.stdout.strip() == "10001"

        command = subprocess.run(
            ["podman", "image", "inspect", "-f", '{{join .Config.Cmd " "}}', default_image],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert command.returncode == 0, command.stderr
        assert "default_workbench_app" in command.stdout
    finally:
        subprocess.run(
            ["podman", "rmi", "-f", default_image],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )


@requires_podman
def test_t5_web_dev_target_builds_and_runs_as_uid_10001():
    """T5: the web dev target builds rc 0 from frontend/ as uid 10001."""
    build = _build_web(WEB_IMAGE)
    assert build.returncode == 0, build.stderr[-4000:]

    inspect = subprocess.run(
        ["podman", "image", "inspect", "-f", "{{.Config.User}}", WEB_IMAGE],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert inspect.returncode == 0, inspect.stderr
    assert inspect.stdout.strip() == "10001"


@requires_podman
def test_t6_web_image_suite_passes_in_image():
    """T6: the web dev image runs the infra-free vitest suite green."""
    run = subprocess.run(
        ["podman", "run", "--rm", WEB_IMAGE, "npm", "run", "test"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    # A green run must have executed tests (T2 analog for vitest).
    assert "passed" in run.stdout


@requires_podman_compose
def test_t8_compose_web_profile_gated_with_loopback_publish():
    """T8: web stays profile-gated; dual-profile render yields the full chain.

    Plain startup must remain postgres-only (spec R5). Starting the
    dashboard requires BOTH profiles — podman-compose does not auto-enable
    depended-on services gated behind another profile (design D6) — and the
    rendered web service must publish loopback-only :5173, mount nothing,
    and depend on api.
    """
    compose = ["podman-compose", "-f", "infra/podman/compose.yaml"]

    plain = subprocess.run(
        [*compose, "config"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    assert plain.returncode == 0, plain.stderr[-2000:]
    assert "web" not in yaml.safe_load(plain.stdout)["services"]

    profiled = subprocess.run(
        [*compose, "--profile", "api", "--profile", "web", "config"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        check=False,
    )
    assert profiled.returncode == 0, profiled.stderr[-2000:]
    services = yaml.safe_load(profiled.stdout)["services"]
    # The dashboard chain is postgres -> api -> web, all three rendered.
    assert {"postgres", "api", "web"} == set(services)

    web = services["web"]
    ports = [str(port) for port in web.get("ports", []) or []]
    assert ports == ["127.0.0.1:5173:5173"], f"web publishes non-loopback: {ports}"
    assert not web.get("volumes"), f"web mounts host paths: {web['volumes']}"
    assert "api" in web.get("depends_on", {}), "web does not depend on api"


def _image_input_paths() -> list[Path]:
    """Tracked inputs whose edits invalidate the composed api/web images."""
    return sorted(
        {
            *PROJECT_ROOT.glob("infra/podman/Containerfile*"),
            *PROJECT_ROOT.glob("frontend/package*.json"),
            *PROJECT_ROOT.glob("frontend/index.html"),
            *PROJECT_ROOT.glob("frontend/vite.config.ts"),
            *PROJECT_ROOT.glob("frontend/tsconfig*.json"),
            *(p for p in (PROJECT_ROOT / "frontend" / "src").rglob("*") if p.is_file()),
        }
    )


def _newest_input_mtime() -> float:
    """Newest input mtime as UTC epoch seconds (stat mtimes are UTC-based)."""
    paths = _image_input_paths()
    assert paths, "no web/api image inputs found under infra/ or frontend/"
    return max(path.stat().st_mtime for path in paths)


def _image_created_unix(tag: str) -> int | None:
    """Image creation time as UTC epoch seconds; None when the tag is absent.

    ``{{.Created.Unix}}`` renders Go's ``time.Time`` directly as an integer
    Unix epoch — already the UTC-normalized timeline, so no RFC3339 parsing
    is needed to compare against stat mtimes.
    """
    proc = subprocess.run(
        ["podman", "image", "inspect", "-f", "{{.Created.Unix}}", tag],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        return None  # absent tag: never composed — tolerated by the guard
    return int(proc.stdout.strip())


def _select_stale(created_by_tag: dict[str, int | None], newest_input: float) -> list[str]:
    """Pure freshness core: present tags created before the newest input.

    Absent tags (``None``) tolerate, and a creation tie counts fresh —
    buildah stamps images after reading inputs, so ``created < mtime`` is
    the only genuinely stale ordering.
    """
    return sorted(
        tag
        for tag, created in created_by_tag.items()
        if created is not None and created < newest_input
    )


def test_select_stale_flags_only_present_tags_older_than_newest_input():
    """Freshness core: only present tags predating the newest input go stale."""
    stale = _select_stale(
        {"podman_api": 100, "podman_web": 300, "podman_postgres": None},
        newest_input=200.0,
    )
    assert stale == ["podman_api"]


def test_select_stale_tolerates_absent_tags_and_creation_ties():
    """Absent tags (never composed) tolerate; equal timestamps count fresh."""
    assert _select_stale({"podman_api": None, "podman_web": None}, 0.0) == []
    assert _select_stale({"podman_api": 200}, 200.0) == []


@requires_podman
def test_t9_composed_images_fresh_against_newest_inputs():
    """T9: composed ``<project>_{api,web}`` images postdate their inputs.

    Freshness compares each composed tag's creation time against the newest
    mtime among its inputs (Containerfiles, package manifests and lockfiles,
    frontend configs, ``frontend/src/**``). Strict image-ID equality is
    unsound — buildah stamps creation at build time, so identical inputs
    legitimately rebuild to different IDs. Absent tags tolerate as a pass
    (the stack was simply never composed). A stale tag fails naming the tag
    and the ``rmi``-rebuild remedy. ``git pull`` bumps input mtimes forward,
    so freshly pulled trees read false-stale — acceptable: the guard fails
    safe toward rebuilding. The remedy uses ``rmi -f`` because a plain rmi
    only untags: the guard-built ``:local`` tags pin identical content, and
    a fully-cached rebuild then resurrects the old image object with its
    original (still stale) creation stamp — drilled live at apply time.
    """
    newest = _newest_input_mtime()
    created_by_tag = {tag: _image_created_unix(tag) for tag in COMPOSED_IMAGE_TAGS}
    stale = _select_stale(created_by_tag, newest)
    assert not stale, (
        f"stale composed image(s) {stale}: tracked inputs changed after the "
        f"images were built; remedy: podman rmi -f {' '.join(stale)} && "
        "podman-compose -f infra/podman/compose.yaml --profile api "
        "--profile web up -d --build"
    )


def _poll_http(
    url: str,
    accept: Callable[[int, str], bool],
    deadline: float,
) -> tuple[int, str]:
    """Poll ``url`` until ``accept(status, body)`` holds or the deadline hits.

    Connection refusals (services still booting) and proxy failure
    signatures (502/504 from the vite proxy, 5xx while uvicorn binds)
    never satisfy ``accept``; they keep polling and surface in the
    deadline failure message instead of aborting early.
    """
    last = "no response yet"
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            pytest.fail(f"{url} never satisfied readiness within E2E_TIMEOUT; last: {last}")
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                status_code, body = response.status, response.read(2048).decode("utf-8", "replace")
        except urllib.error.HTTPError as err:
            status_code = err.code
            body = err.read(2048).decode("utf-8", "replace") if err.fp else ""
        except (OSError, http.client.HTTPException) as err:
            # Refusals/resets while services bind (URLError and raw
            # ConnectionResetError are both OSErrors); retry to deadline.
            last = f"connection error ({getattr(err, 'reason', err)})"
            sleep(min(2.0, remaining))
            continue
        if accept(status_code, body):
            return status_code, body
        last = f"HTTP {status_code}: {body[:120]!r}"
        sleep(min(2.0, remaining))


def _compose_residue(project: str) -> str:
    """Containers/networks still named for the compose project ('' = clean)."""
    ps = subprocess.run(
        ["podman", "ps", "-a", "--filter", f"name={project}", "--format", "{{.Names}}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    networks = subprocess.run(
        ["podman", "network", "ls", "--filter", f"name={project}", "--format", "{{.Name}}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return "\n".join([*ps.stdout.split(), *networks.stdout.split()])


@pytest.mark.skipif(os.environ.get(E2E_GATE_ENV) != "1", reason=f"{E2E_GATE_ENV} != 1")
@requires_podman_compose
def test_e2e_composed_boot_serves_dashboard_chain():
    """Env-gated composed-boot E2E: postgres -> api -> web over real ports.

    Skipped unless ``DAFI_COMPOSED_E2E=1`` (mirrors the ``DAFI_PGVECTOR_SMOKE``
    gating; the default suite stays infra-free). Runs under a unique compose
    project name (``dafi-composed-e2e-<pid>``) so dev stacks cannot collide;
    the documented precondition is host ports 8000/5173 free — a unique
    project cannot free already-published ports. Teardown (``down -v``) runs
    on every outcome in ``try``/``finally``, and a pass additionally asserts
    zero container/network residue.
    """
    project = f"dafi-composed-e2e-{os.getpid()}"
    compose = [
        "podman-compose",
        "-f",
        "infra/podman/compose.yaml",
        "-p",
        project,
        "--profile",
        "api",
        "--profile",
        "web",
    ]
    deadline = monotonic() + E2E_TIMEOUT
    failure: BaseException | None = None
    try:
        up = subprocess.run(
            [*compose, "up", "-d"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=E2E_TIMEOUT,
            check=False,
        )
        assert up.returncode == 0, up.stderr[-4000:] + up.stdout[-2000:]

        _poll_http("http://127.0.0.1:8000/docs", lambda status, _: status == 200, deadline)

        _, root_html = _poll_http(
            "http://127.0.0.1:5173/",
            lambda status, body: status == 200 and 'id="root"' in body,
            deadline,
        )
        assert 'id="root"' in root_html

        # GET /sessions hits the POST-only login route: unauthenticated, the
        # api answers 405 {"detail": "Method Not Allowed"} (verified against
        # the app factory at apply time; 401/200 accepted defensively). A
        # proxy failure (502/504) or refusal never satisfies accept and
        # surfaces as a deadline failure instead.
        _poll_http(
            "http://127.0.0.1:5173/sessions",
            lambda status, _: status in (200, 401, 405),
            deadline,
        )
    except BaseException as exc:  # noqa: BLE001 - teardown must run on any outcome
        failure = exc
        raise
    finally:
        down = subprocess.run(
            [*compose, "down", "-v"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=E2E_TIMEOUT,
            check=False,
        )
        if failure is None:
            assert down.returncode == 0, down.stderr[-2000:]
            residue = _compose_residue(project)
            assert not residue, f"E2E left residue after down -v: {residue}"
