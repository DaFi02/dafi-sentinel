"""LangGraph orchestration for the PR6 workbench.

The orchestration module wraps the deterministic PR1/PR2/PR3/PR4/PR5
services in a state machine. Business logic stays in the services; the
graph only composes them and adds an explicit approval pause before
controlled actions (e.g., chart rendering).

The module re-exports the public symbols from
:mod:`dafi_sentinel.orchestration.graph` and
:mod:`dafi_sentinel.api.services` so callers can ``import`` from the
package root (``from dafi_sentinel.orchestration import
build_investigation_graph, WorkbenchService, sweep_stale_pauses``)
without reaching into the implementation modules.
"""

from dafi_sentinel.api.services import WorkbenchService
from dafi_sentinel.orchestration.graph import (
    APPROVER_PERMISSION,
    ApprovalRequest,
    InvestigationState,
    build_investigation_graph,
    sweep_stale_pauses,
)

# Public re-exports — the dashboard and CLI tools can import the
# orchestration primitives from the package root. The implementation
# lives in ``graph``; this ``__init__`` exists so callers do not have
# to know the internal module layout.
__all__ = [
    "APPROVER_PERMISSION",
    "ApprovalRequest",
    "InvestigationState",
    "WorkbenchService",
    "build_investigation_graph",
    "sweep_stale_pauses",
]
