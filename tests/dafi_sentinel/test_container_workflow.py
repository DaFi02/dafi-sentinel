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
* T7 (always-on): the dedicated ``frontend`` build context denylist
  excludes host artifacts (``node_modules/``, build output, emitted
  config shadows) and itself, so only tracked sources enter web images.

Podman-dependent guards skip cleanly when podman is absent so podman-less
CI stays green (exit 0). No new pytest markers are registered — the
project runs with ``--strict-markers`` — so only the built-in ``skipif``
mark is used. Builds pass ``-f infra/podman/Containerfile`` explicitly
because podman resolves ignorefiles from the context root, not from the
Containerfile directory.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTAINERFILE = "infra/podman/Containerfile"
API_IMAGE = "dafi-sentinel-api:local"
TEST_IMAGE = "dafi-sentinel-test:local"

# Subprocess ceilings from design D7: builds are slow cold, suite runs are
# bounded well below CI job limits.
BUILD_TIMEOUT = 900
RUN_TIMEOUT = 300

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
