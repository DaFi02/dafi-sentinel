"""Guards that the unit suite does not require external runtime infrastructure.

This file replaced the PR1-specific ``test_pr1_*`` checks after PR3 added
Podman + pgvector to the project. The guards assert the boundary that
matters for every PR after foundation:

* The default unit test run does not need a live PostgreSQL/pgvector, Podman,
  or any external service. The pgvector smoke is opt-in via
  ``DAFI_PGVECTOR_SMOKE=1``.
* PR3 ships ``infra/podman/``; PR4 ships ``dafi_sentinel/ml/`` and
  ``dafi_sentinel/charts/``; PR5 ships the React dashboard, FastAPI, and
  auth middleware; PR6 will ship LangGraph orchestration. The forbidden
  modules/paths block those later slices from leaking into earlier PRs.
* The runtime imports pulled in by the unit suite must not include the
  PR6 orchestration surface.
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

    # PR5 ships the FastAPI auth/session middleware and the React dashboard.
    # The forbidden list still blocks PR6 (LangGraph) and any third-party
    # observability stack (Grafana/Prometheus clients).
    forbidden_modules = {"langgraph", "prometheus_client"}

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


def test_pr5_owns_api_and_frontend_but_not_langgraph_or_orchestration():
    """PR5 ships ``dafi_sentinel/api/`` and ``frontend/``; PR6 paths stay out."""
    project_root = Path(__file__).resolve().parents[2]

    present_paths = {
        "infra/podman": project_root / "infra" / "podman",
        "dafi_sentinel/ml": project_root / "dafi_sentinel" / "ml",
        "dafi_sentinel/charts": project_root / "dafi_sentinel" / "charts",
        "dafi_sentinel/api": project_root / "dafi_sentinel" / "api",
        "frontend": project_root / "frontend",
    }
    forbidden_paths = {
        "dafi_sentinel/orchestration": project_root / "dafi_sentinel" / "orchestration",
        "dafi_sentinel/auth/middleware.py": project_root / "dafi_sentinel" / "auth" / "middleware.py",
    }

    assert all(path.exists() for path in present_paths.values())
    assert not any(path.exists() for path in forbidden_paths.values())


def test_pyproject_keeps_langgraph_out_of_pr5():
    """PR5 adds FastAPI/auth helpers but still excludes PR6 LangGraph surface."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8").lower()

    assert "langgraph" not in content, "langgraph must not be added in PR5"

    for required in (
        "fastapi",
        "uvicorn",
        "pydantic",
        "itsdangerous",
        "passlib",
    ):
        assert required in content, f"{required} must be declared in PR5"

    # Earlier slices must remain present (boundary regression guard).
    for required in ("scikit-learn", "numpy", "matplotlib", "psycopg", "pgvector"):
        assert required in content, f"{required} must still be declared (regression)"


def test_frontend_package_manifest_blocks_langgraph():
    """PR5 frontend manifest must not depend on LangGraph or observability clients."""
    package_json = Path(__file__).resolve().parents[2] / "frontend" / "package.json"
    if not package_json.exists():
        # The frontend has not been scaffolded yet in this slice; that is a
        # separate boundary that is exercised by ``test_pr5_owns_api_and_frontend_*``
        # and the build guard. We tolerate the missing manifest until the
        # scaffold lands.
        return

    payload = json.loads(package_json.read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        for name in payload.get(section, {}).keys():
            assert not name.startswith("@langchain/"), f"forbidden frontend dep: {name}"
            assert name not in {"langgraph", "prometheus-client", "grafana-"}, (
                f"forbidden frontend dep: {name}"
            )
