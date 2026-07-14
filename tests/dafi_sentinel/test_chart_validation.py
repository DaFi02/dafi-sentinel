"""Tests for the chart-spec validation layer.

The chart renderer in PR4 must reject any ``ChartSpec`` that the
dashboard cannot safely render: empty titles, missing evidence
citations, or missing axis fields for non-table charts. The validation
is the single source of truth for what the renderer will accept.
"""

from __future__ import annotations

import pytest

from dafi_sentinel.charts import validation
from dafi_sentinel.domain.models import ChartSpec


def _line_spec(**overrides) -> ChartSpec:
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
    validation.validate_chart_spec(_line_spec())  # should not raise


def test_validation_rejects_empty_title():
    """An empty title is meaningless to the dashboard reviewer."""
    spec = _line_spec(title="")
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "title"


def test_validation_rejects_whitespace_only_title():
    """A whitespace-only title is just as invalid as an empty one."""
    spec = _line_spec(title="   ")
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "title"


def test_validation_rejects_missing_evidence_ids():
    """Every chart must cite at least one evidence ID for audit traceability."""
    spec = _line_spec(evidence_ids=())
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "evidence_ids"


def test_validation_rejects_empty_string_evidence_id():
    """An evidence ID of "" inside the tuple is not a valid citation."""
    spec = _line_spec(evidence_ids=("",))
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "evidence_ids"


def test_validation_rejects_line_chart_missing_x_axis():
    """A line chart without an x axis cannot be rendered."""
    spec = _line_spec(x="")
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "x"


def test_validation_rejects_bar_chart_missing_y_axis():
    """A bar chart without a y axis cannot be rendered."""
    spec = _line_spec(kind="bar", y="   ")
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "y"


def test_validation_rejects_scatter_chart_missing_y_axis():
    """A scatter chart without a y axis cannot be rendered."""
    spec = _line_spec(kind="scatter", y="")
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "y"


def test_table_chart_with_empty_axes_is_valid():
    """A table chart intentionally has no x/y axes — it lists the evidence rows."""
    spec = _line_spec(kind="table", x="", y="", evidence_ids=("ev-1", "ev-2"))
    validation.validate_chart_spec(spec)  # should not raise


def test_table_chart_with_optional_column_hints_is_valid():
    """A table chart can hint at column names but is not required to."""
    spec = _line_spec(kind="table", x="column_a", y="column_b", evidence_ids=("ev-1",))
    validation.validate_chart_spec(spec)  # should not raise


def test_chart_validation_error_carries_field_and_reason():
    """The error must surface field + reason for the dashboard to render a useful message."""
    spec = _line_spec(evidence_ids=())
    with pytest.raises(validation.ChartValidationError) as failure:
        validation.validate_chart_spec(spec)
    assert failure.value.field == "evidence_ids"
    assert failure.value.reason
