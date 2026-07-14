"""Tests for the chart-spec validation layer.

The chart renderer in PR4 must reject any ``ChartSpec`` that the
dashboard cannot safely render: empty titles, missing evidence
citations, or missing axis fields for non-table charts. The validation
is the single source of truth for what the renderer will accept.
"""

from __future__ import annotations

import pytest

from dafi_sentinel.charts import validation
from dafi_sentinel.charts.validation import ChartValidationError
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


def test_valid_line_chart_spec_passes_validation():
    """A well-formed line chart must validate without error."""
    validation.validate_chart_spec(_spec())


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"title": ""}, "title"),
        ({"title": "   "}, "title"),
        ({"evidence_ids": ()}, "evidence_ids"),
        ({"evidence_ids": ("",)}, "evidence_ids"),
        ({"x": ""}, "x"),
        ({"kind": "bar", "y": "   "}, "y"),
        ({"kind": "scatter", "y": ""}, "y"),
    ],
)
def test_validation_rejects_invalid_field(overrides, field):
    """Each invalid field on a non-table chart must raise with that field name."""
    with pytest.raises(ChartValidationError) as failure:
        validation.validate_chart_spec(_spec(**overrides))
    assert failure.value.field == field
    assert failure.value.reason


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "table", "x": "", "y": "", "evidence_ids": ("ev-1", "ev-2")},
        {"kind": "table", "x": "column_a", "y": "column_b", "evidence_ids": ("ev-1",)},
    ],
)
def test_table_chart_with_or_without_axes_is_valid(overrides):
    """Table charts treat evidence rows as the body; axes are optional hints."""
    validation.validate_chart_spec(_spec(**overrides))
