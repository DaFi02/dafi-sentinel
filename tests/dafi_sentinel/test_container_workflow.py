"""CI-safe guards for the rootless Podman container workflow.

These tests assert the container contracts shipped by the
``podman-containerization`` change (specs containerized-backend-workflow,
design D7):

* T0 (always-on): the build-context denylist excludes host artifacts
  (``**/.venv/``, ``.git/``) so host virtualenvs never enter an image.
* T1: the ``runtime`` target builds and the image runs as uid 10001.
* T2: the ``test`` target builds and the default suite passes in-image
  (a nonzero exit, including pytest's exit-5 empty-collection code, fails).
* T3: the compose file renders and the api service is profile-gated
  (plain config stays postgres-only).

Podman-dependent guards skip cleanly when podman is absent so podman-less
CI stays green (exit 0). No new pytest markers are registered — the
project runs with ``--strict-markers`` — so only the built-in ``skipif``
mark is used. Builds must use the explicit ``-f infra/podman/Containerfile``
form because the Containerfile lives outside the repo-root build context.
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
    assert "api" in yaml.safe_load(profiled.stdout)["services"]
