"""Chart-spec validation for the PR4 renderer.

The dashboard rejects any chart that cannot be safely rendered or
audited. Validation is a pure function over the domain ``ChartSpec``
contract: no matplotlib, no I/O, no global state. The renderer
assumes a validated spec.
"""

from __future__ import annotations

from dafi_sentinel.domain.models import ChartSpec


_AXIS_REQUIRED_KINDS = frozenset({"line", "bar", "scatter"})


class ChartValidationError(ValueError):
    """Raised when a ``ChartSpec`` is not safe for the renderer."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"chart spec invalid: {field}: {reason}")


def _is_blank(value: str) -> bool:
    return not value or not value.strip()


def validate_chart_spec(spec: ChartSpec) -> None:
    """Validate a ``ChartSpec`` for the renderer.

    Raises ``ChartValidationError`` when the spec is missing a title,
    evidence citation, or required axis field. Table charts may omit
    ``x`` and ``y`` because the renderer treats the evidence rows as
    the table body.
    """
    if _is_blank(spec.title):
        raise ChartValidationError("title", "title must be a non-empty string")

    if not spec.evidence_ids:
        raise ChartValidationError("evidence_ids", "chart must cite at least one evidence id")
    if any(_is_blank(evidence_id) for evidence_id in spec.evidence_ids):
        raise ChartValidationError("evidence_ids", "evidence ids must be non-empty strings")

    if spec.kind in _AXIS_REQUIRED_KINDS:
        if _is_blank(spec.x):
            raise ChartValidationError("x", f"x axis is required for {spec.kind} charts")
        if _is_blank(spec.y):
            raise ChartValidationError("y", f"y axis is required for {spec.kind} charts")
    # "table" charts treat the evidence rows as the table body; x/y are
    # optional column hints and may be empty.
