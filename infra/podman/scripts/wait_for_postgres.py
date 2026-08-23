#!/usr/bin/env python3
"""Block until PostgreSQL answers a probe query, then exec the real command.

Baked into every container image at /opt/dafi/wait_for_postgres.py (design
D4) so container readiness never depends on compose healthcheck support:

    python /opt/dafi/wait_for_postgres.py \
        uvicorn dafi_sentinel.api.app:default_workbench_app --host 0.0.0.0 ...

Behavior:
- Requires ``DAFI_PGVECTOR_DSN`` in the environment.
- Polls ``SELECT 1`` over psycopg once per second.
- Gives up after ``WAIT_TIMEOUT`` seconds (default 60): prints diagnostics to
  stderr and exits 1.
- On success prints progress to stderr and replaces itself with the remaining
  argv via ``os.execvp``, so the execed process inherits PID 1 signal
  semantics inside the container.
"""

import os
import sys
import time

import psycopg

POLL_INTERVAL_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 60.0
CONNECT_TIMEOUT_SECONDS = 3


def fail(message):
    """Print a diagnostic to stderr and exit 1 (spec R5 timeout scenario)."""
    print(f"wait_for_postgres: {message}", file=sys.stderr)
    sys.exit(1)


def probe_once(dsn):
    """Succeed silently when PostgreSQL answers SELECT 1; raise otherwise."""
    # psycopg closes the connection when the context manager exits.
    with psycopg.connect(dsn, connect_timeout=CONNECT_TIMEOUT_SECONDS) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()


def main():
    dsn = os.environ.get("DAFI_PGVECTOR_DSN")
    if not dsn:
        fail("DAFI_PGVECTOR_DSN is not set; cannot probe PostgreSQL.")

    # Validate usage BEFORE any polling so a missing command fails fast
    # instead of burning the whole readiness deadline first.
    command = sys.argv[1:]
    if not command:
        fail("No command supplied to exec after readiness (usage: wait_for_postgres.py CMD [ARGS...]).")

    raw_timeout = os.environ.get("WAIT_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(raw_timeout)
    except ValueError:
        fail(f"WAIT_TIMEOUT must be numeric, got {raw_timeout!r}.")

    deadline = time.monotonic() + timeout
    while True:
        try:
            probe_once(dsn)
            break
        except psycopg.Error as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fail(
                    f"PostgreSQL not reachable within {timeout:g}s: "
                    f"{type(exc).__name__}: {exc}. "
                    "Check DAFI_PGVECTOR_DSN and that the database service is up."
                )
            print(
                f"wait_for_postgres: PostgreSQL unavailable "
                f"({type(exc).__name__}); retrying in {POLL_INTERVAL_SECONDS:g}s...",
                file=sys.stderr,
            )
            time.sleep(min(POLL_INTERVAL_SECONDS, remaining))

    print("wait_for_postgres: PostgreSQL is ready; handing off.", file=sys.stderr)

    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
