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


def collect_chart_spec_errors(spec: ChartSpec) -> tuple[ChartValidationError, ...]:
    """Return every validation problem on a ``ChartSpec`` in a single pass.

    R3 F17: a spec with multiple invalid fields (e.g., blank ``title``
    AND empty ``evidence_ids`` AND blank ``x``) previously surfaced
    one error per call to :func:`validate_chart_spec`. The collector
    walks the spec once and returns the full list of problems so
    the dashboard can render a complete error summary in one round
    trip. The implementation is deterministic (errors are emitted
    in field order: title, evidence_ids, x, y) so the test surface
    is stable.
    """
    errors: list[ChartValidationError] = []
    if _is_blank(spec.title):
        errors.append(ChartValidationError("title", "title must be a non-empty string"))

    if not spec.evidence_ids:
        errors.append(ChartValidationError("evidence_ids", "chart must cite at least one evidence id"))
    if any(_is_blank(evidence_id) for evidence_id in spec.evidence_ids):
        errors.append(ChartValidationError("evidence_ids", "evidence ids must be non-empty strings"))

    if spec.kind in _AXIS_REQUIRED_KINDS:
        if _is_blank(spec.x):
            errors.append(ChartValidationError("x", f"x axis is required for {spec.kind} charts"))
        if _is_blank(spec.y):
            errors.append(ChartValidationError("y", f"y axis is required for {spec.kind} charts"))
    # "table" charts treat the evidence rows as the table body; x/y
    # are optional column hints and may be empty.
    return tuple(errors)


def validate_chart_spec(spec: ChartSpec) -> None:
    """Validate a ``ChartSpec`` for the renderer.

    Raises ``ChartValidationError`` on the first invalid field. The
    back-compat surface is preserved; callers that want the full
    error list use :func:`collect_chart_spec_errors` instead. The
    two stay in sync because the raising version delegates to the
    collector and raises the first error.
    """
    errors = collect_chart_spec_errors(spec)
    if errors:
        raise errors[0]
