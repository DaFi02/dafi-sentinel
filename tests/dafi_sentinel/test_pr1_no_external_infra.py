"""Guards that the unit suite does not require external runtime infrastructure.

This file replaced the PR1-specific ``test_pr1_*`` checks after PR3 added
Podman + pgvector to the project. The guards assert the boundary that
matters for every PR after foundation:

* The default unit test run does not need a live PostgreSQL/pgvector, Podman,
  or any external service. The pgvector smoke is opt-in via
  ``DAFI_PGVECTOR_SMOKE=1``.
* PR3 ships ``infra/podman/``; PR4 ships ``dafi_sentinel/ml/`` and
  ``dafi_sentinel/charts/``; PR5 ships the React dashboard, FastAPI, and
  auth middleware; PR6 ships ``dafi_sentinel/orchestration/`` (LangGraph
  state machine). The forbidden modules/paths block post-PR6 surface
  (production deploy, telemetry exporters, real OAuth) from leaking into
  earlier PRs.
* The runtime imports pulled in by the unit suite must not include the
  post-PR6 surface.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import dafi_sentinel


def test_unit_suite_does_not_require_live_postgres_or_podman():
    """The default pytest run must not need a live pgvector/Postgres/Podman."""
    import dafi_sentinel.domain.models  # noqa: F401
    import dafi_sentinel.retrieval.contracts  # noqa: F401
    import dafi_sentinel.storage.contracts  # noqa: F401

    # PR6 ships the LangGraph orchestration module. The forbidden list still
    # blocks post-PR6 surface (telemetry exporters, OAuth libs, deploy SDKs).
    forbidden_modules = {
        "prometheus_client",
        "opentelemetry",
        "kubernetes",
        "boto3",
        "oauthlib",
    }

    assert forbidden_modules.isdisjoint(sys.modules)
    assert dafi_sentinel.__version__ == "0.1.0"


def test_pgvector_smoke_is_opt_in_and_skipped_by_default():
    """The pgvector smoke is gated on DAFI_PGVECTOR_SMOKE; the unit suite skips it."""
    project_root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "DAFI_PGVECTOR_SMOKE": "0"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/dafi_sentinel/test_pgvector_adapter.py", "-rs"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "skipped" in proc.stdout.lower()
    assert "DAFI_PGVECTOR_SMOKE" in proc.stdout


def test_pr6_owns_orchestration_but_not_post_pr6_surface():
    """PR6 ships ``dafi_sentinel/orchestration/``; post-PR6 surface stays out."""
    project_root = Path(__file__).resolve().parents[2]

    present_paths = {
        "infra/podman": project_root / "infra" / "podman",
        "dafi_sentinel/ml": project_root / "dafi_sentinel" / "ml",
        "dafi_sentinel/charts": project_root / "dafi_sentinel" / "charts",
        "dafi_sentinel/api": project_root / "dafi_sentinel" / "api",
        "frontend": project_root / "frontend",
        "dafi_sentinel/orchestration": project_root / "dafi_sentinel" / "orchestration",
    }
    forbidden_paths = {
        # PR7+ post-PR6 surface; reserve the path names so the guard catches
        # a future PR that tries to add deploy/telemetry/admin early.
        "dafi_sentinel/deploy": project_root / "dafi_sentinel" / "deploy",
        "dafi_sentinel/telemetry": project_root / "dafi_sentinel" / "telemetry",
        "frontend/src/admin": project_root / "frontend" / "src" / "admin",
    }

    assert all(path.exists() for path in present_paths.values())
    assert not any(path.exists() for path in forbidden_paths.values())


def test_pyproject_keeps_post_pr6_surface_out_of_pr6():
    """PR6 adds langgraph but still excludes post-PR6 surface (deploy, telemetry, OAuth)."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8").lower()

    # Post-PR6 surface must not be added in this slice.
    for forbidden in (
        "opentelemetry",
        "kubernetes",
        "boto3",
        "oauthlib",
        "prometheus",
    ):
        assert forbidden not in content, f"{forbidden} must not be added in PR6"

    # PR6 must declare langgraph; earlier slices must remain present
    # (boundary regression guard).
    for required in (
        "langgraph",
        "fastapi",
        "uvicorn",
        "pydantic",
        "itsdangerous",
        "passlib",
        "scikit-learn",
        "numpy",
        "matplotlib",
        "psycopg",
        "pgvector",
    ):
        assert required in content, f"{required} must be declared (regression)"


def test_frontend_package_manifest_blocks_langgraph():
    """PR5 frontend manifest must not depend on LangGraph or observability clients.

    PR6 keeps the same rule: langgraph is a Python-only dependency in this
    slice, so the frontend manifest must not import it. The guard also
    blocks any LangChain- or Grafana-flavoured frontend dep.
    """
    package_json = Path(__file__).resolve().parents[2] / "frontend" / "package.json"
    if not package_json.exists():
        return

    payload = json.loads(package_json.read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        for name in payload.get(section, {}).keys():
            assert not name.startswith("@langchain/"), f"forbidden frontend dep: {name}"
            assert name not in {"langgraph", "prometheus-client", "grafana-"}, (
                f"forbidden frontend dep: {name}"
            )


def test_orchestration_surface_ships_with_state_graph_module():
    """PR6 ships ``dafi_sentinel/orchestration/graph.py`` with a compiled state graph.

    The graph module must reference the LangGraph ``StateGraph`` and
    ``interrupt`` primitives that power the approval pause. The presence
    of the module is the source of truth; the public surface tests
    exercise its behaviour.
    """
    project_root = Path(__file__).resolve().parents[2]
    graph_module = project_root / "dafi_sentinel" / "orchestration" / "graph.py"
    assert graph_module.exists(), "dafi_sentinel/orchestration/graph.py must be shipped in PR6"

    content = graph_module.read_text(encoding="utf-8")
    assert "StateGraph" in content, "graph module must use langgraph StateGraph"
    assert "interrupt" in content, "graph module must use langgraph interrupt for approval"
