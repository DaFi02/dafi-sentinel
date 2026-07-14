"""Guards that the unit suite does not require external runtime infrastructure.

This file replaced the PR1-specific ``test_pr1_*`` checks after PR3 added
Podman + pgvector to the project. The guards assert the boundary that
matters for every PR after foundation:

* The default unit test run does not need a live PostgreSQL/pgvector, Podman,
  or any external service. The pgvector smoke is opt-in via
  ``DAFI_PGVECTOR_SMOKE=1``.
* PR3 ships ``infra/podman/``; PR4 ships ``dafi_sentinel/ml/`` and
  ``dafi_sentinel/charts/``; PR5 will ship the React dashboard, FastAPI,
  and auth middleware; PR6 will ship LangGraph orchestration. The forbidden
  modules/paths block those later slices from leaking into earlier PRs.
* The runtime imports pulled in by the unit suite must not include
  api/dashboard/auth/middleware/orchestration modules.
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

    # PR4 (ML/charts) makes scikit-learn/numpy/matplotlib a runtime dependency.
    # The forbidden list still blocks PR5 (FastAPI/React/auth) and PR6 (LangGraph).
    forbidden_modules = {"fastapi", "langgraph", "prometheus_client"}

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


def test_pr4_owns_ml_and_charts_but_not_frontend_api_auth_or_langgraph():
    """PR4 ships ``dafi_sentinel/ml/`` and ``dafi_sentinel/charts/``; PR5/PR6 paths stay out."""
    project_root = Path(__file__).resolve().parents[2]

    present_paths = {
        "infra/podman": project_root / "infra" / "podman",
        "dafi_sentinel/ml": project_root / "dafi_sentinel" / "ml",
        "dafi_sentinel/charts": project_root / "dafi_sentinel" / "charts",
    }
    forbidden_paths = {
        "frontend": project_root / "frontend",
        "dafi_sentinel/api": project_root / "dafi_sentinel" / "api",
        "dafi_sentinel/auth": project_root / "dafi_sentinel" / "auth",
        "dafi_sentinel/security/middleware": project_root / "dafi_sentinel" / "security" / "middleware.py",
        "dafi_sentinel/orchestration": project_root / "dafi_sentinel" / "orchestration",
    }

    assert all(path.exists() for path in present_paths.values())
    assert not any(path.exists() for path in forbidden_paths.values())


def test_pyproject_keeps_frontend_api_auth_langgraph_out_of_pr4():
    """PR4 adds scikit-learn/numpy/matplotlib but still excludes PR5/PR6 surface."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8").lower()

    for forbidden in ("fastapi", "react", "langgraph"):
        assert forbidden not in content, f"{forbidden} must not be added in PR4"

    for required in ("scikit-learn", "numpy", "matplotlib"):
        assert required in content, f"{required} must be declared in PR4"

    assert "psycopg" in content
    assert "pgvector" in content
