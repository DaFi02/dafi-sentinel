"""Guards that the unit suite does not require external runtime infrastructure.

This file replaced the PR1-specific ``test_pr1_*`` checks after PR3 added
Podman + pgvector to the project. The guards now assert the boundary that
matters for every PR after foundation:

* The default unit test run does not need a live PostgreSQL/pgvector, Podman,
  or any external service. The pgvector smoke is opt-in via
  ``DAFI_PGVECTOR_SMOKE=1``.
* PR3-onwards infrastructure lives under ``infra/podman/``; PR5/frontend,
  PR4/ML, and PR6/LangGraph do not.
* The runtime imports pulled in by the unit suite do not include
  api/dashboard/auth/middleware/ML/orchestration modules.
"""

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

    forbidden_modules = {"fastapi", "langgraph", "sklearn", "prometheus_client"}

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


def test_pr3_owns_podman_infra_but_not_frontend_ml_api_or_langgraph():
    """PR3 ships infra/podman only; frontend, ML, API/auth middleware, and LangGraph stay out."""
    project_root = Path(__file__).resolve().parents[2]

    present_paths = {
        "infra/podman": project_root / "infra" / "podman",
    }
    forbidden_paths = {
        "frontend": project_root / "frontend",
        "dafi_sentinel/api": project_root / "dafi_sentinel" / "api",
        "dafi_sentinel/auth": project_root / "dafi_sentinel" / "auth",
        "dafi_sentinel/security/middleware": project_root / "dafi_sentinel" / "security" / "middleware.py",
        "dafi_sentinel/ml": project_root / "dafi_sentinel" / "ml",
        "dafi_sentinel/orchestration": project_root / "dafi_sentinel" / "orchestration",
    }

    assert all(path.exists() for path in present_paths.values())
    assert not any(path.exists() for path in forbidden_paths.values())


def test_pyproject_keeps_frontend_ml_api_langgraph_out_of_pr3():
    """Dependencies and names declared in pyproject are limited to PR3 scope."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8").lower()

    for forbidden in ("fastapi", "react", "sklearn", "numpy", "matplotlib", "langgraph"):
        assert forbidden not in content, f"{forbidden} must not be added in PR3"

    assert "psycopg" in content
    assert "pgvector" in content
