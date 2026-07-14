"""Tests for the orchestration package public exports (R2 med).

The 4R review caught that the orchestration package's ``__init__``
module documented the public surface but did not re-export the
symbols, so callers had to reach into ``dafi_sentinel.orchestration.graph``
directly. The fix lifts the canonical names (``build_investigation_graph``,
``sweep_stale_pauses``, ``WorkbenchService``, ``ApprovalRequest``,
``InvestigationState``, ``APPROVER_PERMISSION``) into ``__init__`` so
``from dafi_sentinel.orchestration import build_investigation_graph``
works. The implementation still lives in ``graph.py``; this test
pins the re-export contract so a future refactor of the internal
module layout does not silently break the public surface.
"""

from __future__ import annotations


def test_orchestration_package_reexports_graph_factory():
    """``build_investigation_graph`` is importable from the package root."""
    from dafi_sentinel.orchestration import build_investigation_graph

    assert callable(build_investigation_graph)


def test_orchestration_package_reexports_sweeper():
    """``sweep_stale_pauses`` is importable from the package root."""
    from dafi_sentinel.orchestration import sweep_stale_pauses

    assert callable(sweep_stale_pauses)


def test_orchestration_package_reexports_workbench_service():
    """``WorkbenchService`` is importable from the package root.

    The workbench service is the seam between the orchestration graph
    and the deterministic services; the orchestration package owns
    the public re-export so callers do not have to know whether the
    implementation lives in ``api.services`` or ``orchestration``.
    """
    from dafi_sentinel.orchestration import WorkbenchService

    from dafi_sentinel.api.services import WorkbenchService as ApiWorkbenchService

    assert WorkbenchService is ApiWorkbenchService


def test_orchestration_package_reexports_state_and_approval_contracts():
    """The TypedDict, payload dataclass, and permission constant are re-exported."""
    from dafi_sentinel.orchestration import (
        APPROVER_PERMISSION,
        ApprovalRequest,
        InvestigationState,
    )

    assert APPROVER_PERMISSION == "approval:grant"
    assert ApprovalRequest.__name__ == "ApprovalRequest"
    assert InvestigationState.__name__ == "InvestigationState"
