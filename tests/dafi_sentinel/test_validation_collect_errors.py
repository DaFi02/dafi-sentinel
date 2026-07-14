"""Tests for the chart-spec multi-error collector (R3 F17).

The 4R review caught that ``validate_chart_spec`` raised on the
first invalid field, so a spec with multiple problems (e.g., blank
``title`` AND empty ``evidence_ids`` AND blank ``x``) only surfaced
one error per call. The dashboard had to re-submit the spec
repeatedly to discover every issue. The fix introduces a
``collect_chart_spec_errors`` helper that returns every problem in
a single pass so the renderer / API can surface all of them at
once. The existing ``validate_chart_spec`` keeps its raise-on-first
behavior for backward compatibility, but uses the collector
internally so the two stay in sync.
"""

from __future__ import annotations

import pytest

from dafi_sentinel.charts.validation import (
    ChartValidationError,
    collect_chart_spec_errors,
    validate_chart_spec,
)
from dafi_sentinel.domain.models import ChartSpec


def _spec(**overrides) -> ChartSpec:
    defaults = {
        "kind": "line",
        "title": "Error rate over time",
        "x": "timestamp",
        "y": "errors",
        "evidence_ids": ("ev-1",),
    }
    defaults.update(overrides)
    return ChartSpec(**defaults)


@pytest.mark.parametrize(
    "overrides, expected_fields",
    [
        # 1. title + evidence_ids + x all bad on a non-table chart
        (
            {"title": "", "evidence_ids": (), "x": ""},
            {"title", "evidence_ids", "x"},
        ),
        # 2. evidence_ids has a blank entry AND y is blank
        (
            {"evidence_ids": ("",), "y": "   "},
            {"evidence_ids", "y"},
        ),
        # 3. all four required fields bad on a scatter chart
        (
            {"kind": "scatter", "title": "  ", "evidence_ids": (), "x": "", "y": ""},
            {"title", "evidence_ids", "x", "y"},
        ),
    ],
)
def test_validation_collects_multiple_errors_per_row(overrides, expected_fields):
    """The collector returns every invalid field in a single pass.

    R3 F17: a spec with multiple problems must surface all of them
    so the dashboard can render a complete error list. The
    parametrized cases triangulate the common combinations
    (non-table + table, evidence ids, axis fields).
    """
    errors = collect_chart_spec_errors(_spec(**overrides))
    actual_fields = {error.field for error in errors}
    assert actual_fields == expected_fields, (
        f"collector must return all expected fields; got {actual_fields}, "
        f"expected {expected_fields}"
    )


def test_collect_returns_empty_tuple_for_valid_spec():
    """A valid spec produces no errors (sanity check)."""
    errors = collect_chart_spec_errors(_spec())
    assert errors == ()


def test_collect_does_not_raise():
    """The collector must never raise — it returns the error list."""
    # A spec with every field bad should NOT raise; the collector
    # returns a tuple of ChartValidationError instances instead.
    spec = _spec(title="", evidence_ids=(), x="", y="")
    errors = collect_chart_spec_errors(spec)
    assert len(errors) >= 4
    for error in errors:
        assert isinstance(error, ChartValidationError)


def test_validate_chart_spec_still_raises_on_first_error_for_back_compat():
    """The existing raise-on-first behavior is preserved for callers that expect it.

    R3 F17 keeps the public ``validate_chart_spec`` surface
    unchanged so the renderer / API do not need to learn a new
    contract. The collector is the new seam.
    """
    with pytest.raises(ChartValidationError) as failure:
        validate_chart_spec(_spec(title="", evidence_ids=(), x=""))
    # The first invalid field wins (deterministic order: title, then
    # evidence_ids, then axis fields).
    assert failure.value.field == "title"
