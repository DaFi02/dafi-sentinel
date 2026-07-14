import sys
from pathlib import Path

import dafi_sentinel


def test_pr1_imports_do_not_load_external_infrastructure_modules():
    import dafi_sentinel.domain.models  # noqa: F401
    import dafi_sentinel.retrieval.contracts  # noqa: F401
    import dafi_sentinel.storage.contracts  # noqa: F401

    forbidden_modules = {"psycopg", "pgvector", "fastapi", "langgraph", "sklearn", "prometheus_client"}

    assert forbidden_modules.isdisjoint(sys.modules)
    assert dafi_sentinel.__version__ == "0.1.0"


def test_pr1_has_no_infra_frontend_or_auth_middleware_files():
    project_root = Path(__file__).resolve().parents[2]
    forbidden_paths = [project_root / "infra" / "podman", project_root / "frontend", project_root / "dafi_sentinel" / "api", project_root / "dafi_sentinel" / "security" / "middleware.py", project_root / "dafi_sentinel" / "auth"]

    assert [path for path in forbidden_paths if path.exists()] == []


def test_pr1_pyproject_declares_only_pytest_dev_dependency():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8").lower()

    for forbidden in ("psycopg", "pgvector", "podman", "grafana", "prometheus", "langgraph", "fastapi", "react"):
        assert forbidden not in content
    assert "pytest" in content
