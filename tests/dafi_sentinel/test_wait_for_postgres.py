"""Unit tests for the container readiness handoff script.

These cover the ``wait_for_postgres.py`` contract (spec R5) without any
container or network: the psycopg connection and the clock are faked, so
every branch is deterministic and runs on podman-less hosts too.
"""

import importlib.util
import os
import sys
from pathlib import Path

import psycopg
import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "infra"
    / "podman"
    / "scripts"
    / "wait_for_postgres.py"
)
if not SCRIPT_PATH.exists():
    # In-image runs have no build context: exercise the copy baked into
    # the image at /opt/dafi instead of the repo checkout path.
    SCRIPT_PATH = Path("/opt/dafi/wait_for_postgres.py")


@pytest.fixture()
def script(monkeypatch):
    """Load the baked script as a module and isolate argv/env per test."""
    spec = importlib.util.spec_from_file_location("wait_for_postgres", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["wait_for_postgres.py"])
    return module


def _refuse_connection(*_args, **_kwargs):
    raise AssertionError("psycopg.connect must not be called on this path")


def test_missing_dsn_fails_before_any_connection(script, monkeypatch, capsys):
    monkeypatch.delenv("DAFI_PGVECTOR_DSN", raising=False)
    monkeypatch.setattr(script.psycopg, "connect", _refuse_connection)

    with pytest.raises(SystemExit) as excinfo:
        script.main()

    assert excinfo.value.code == 1
    assert "DAFI_PGVECTOR_DSN" in capsys.readouterr().err


def test_non_numeric_wait_timeout_fails_fast(script, monkeypatch, capsys):
    monkeypatch.setenv("DAFI_PGVECTOR_DSN", "postgresql://x")
    monkeypatch.setenv("WAIT_TIMEOUT", "soon")
    monkeypatch.setattr(sys, "argv", ["wait_for_postgres.py", "uvicorn"])
    monkeypatch.setattr(script.psycopg, "connect", _refuse_connection)

    with pytest.raises(SystemExit) as excinfo:
        script.main()

    assert excinfo.value.code == 1
    assert "WAIT_TIMEOUT" in capsys.readouterr().err


def test_missing_command_fails_before_polling(script, monkeypatch, capsys):
    """Usage validation happens before the poll loop (no wasted deadline)."""
    monkeypatch.setenv("DAFI_PGVECTOR_DSN", "postgresql://x")
    monkeypatch.setattr(script.time, "sleep", _refuse_connection)
    monkeypatch.setattr(script.psycopg, "connect", _refuse_connection)

    with pytest.raises(SystemExit) as excinfo:
        script.main()

    assert excinfo.value.code == 1
    assert "No command supplied" in capsys.readouterr().err


def test_timeout_exits_1_with_diagnostics(script, monkeypatch, capsys):
    monkeypatch.setenv("DAFI_PGVECTOR_DSN", "postgresql://x")
    monkeypatch.setenv("WAIT_TIMEOUT", "2")
    monkeypatch.setattr(sys, "argv", ["wait_for_postgres.py", "uvicorn", "--port", "8000"])

    def always_unreachable(_dsn):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(script, "probe_once", always_unreachable)
    clock = iter([0.0, 1.0, 3.0])  # start, first retry check, exhausted deadline
    monkeypatch.setattr(script.time, "monotonic", lambda: next(clock))
    sleeps = []
    monkeypatch.setattr(script.time, "sleep", sleeps.append)

    with pytest.raises(SystemExit) as excinfo:
        script.main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "not reachable within 2s" in captured.err
    assert sleeps == [1.0]  # one bounded retry before giving up


def test_success_hands_off_to_execvp(script, monkeypatch):
    monkeypatch.setenv("DAFI_PGVECTOR_DSN", "postgresql://x")
    monkeypatch.setattr(sys, "argv", ["wait_for_postgres.py", "uvicorn", "--host", "0.0.0.0"])
    monkeypatch.setattr(script, "probe_once", lambda _dsn: None)
    execed = {}
    monkeypatch.setattr(
        os,
        "execvp",
        lambda program, args: execed.update(program=program, args=args),
    )

    script.main()  # returns only because execvp is faked

    assert execed == {"program": "uvicorn", "args": ["uvicorn", "--host", "0.0.0.0"]}


def test_probe_once_runs_select_over_psycopg(script, monkeypatch):
    seen = {}

    class FakeCursor:
        def __init__(self, conn):
            self._conn = conn

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql):
            seen["sql"] = sql

        def fetchone(self):
            return (1,)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            seen["closed"] = True
            return False

        def cursor(self):
            return FakeCursor(self)

    def fake_connect(dsn, connect_timeout=None):
        seen["dsn"] = dsn
        seen["connect_timeout"] = connect_timeout
        return FakeConnection()

    monkeypatch.setattr(script.psycopg, "connect", fake_connect)

    dsn = "postgresql://sentinel:sentinel@postgres:5432/sentinel"
    assert script.probe_once(dsn) is None
    assert seen["dsn"] == dsn
    assert seen["sql"] == "SELECT 1"
    assert seen["closed"] is True
