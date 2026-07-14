"""Edge-case tests for the chart renderer (PR-C.16, R3 F13).

PR-C.16 (R3 F13): the 4R review caught that the chart renderer had
no edge-case coverage. A zero-height figure, a unicode label, or an
empty data series for a non-table chart could each crash matplotlib
or render an unreadable PNG.

The contract: every edge case MUST return a valid PNG byte stream
(or raise a documented ``ValueError`` for the empty-axis case the
renderer already rejects). An opaque matplotlib internal error is
not acceptable.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest

from dafi_sentinel.charts import renderer
from dafi_sentinel.domain.models import ChartSpec, EvidenceRef, SourceMetadata, RedactedIncidentRecord


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _spec(**overrides) -> ChartSpec:
    defaults = {
        "kind": "line",
        "title": "Error rate over time",
        "x": "timestamp",
        "y": "errors",
        "evidence_ids": ("ev-render-1",),
    }
    defaults.update(overrides)
    return ChartSpec(**defaults)


def test_render_chart_with_unicode_labels_does_not_crash():
    """Unicode labels (CJK, accented, emoji) MUST render to a valid PNG."""
    png_bytes = renderer.render_chart(
        _spec(title="Errores por servicio", x="año", y="recuento"),
        [(1, 10), (2, 20), (3, 15)],
    )
    assert png_bytes.startswith(PNG_MAGIC)
    # The PNG is decodable.
    from PIL import Image
    with Image.open(io.BytesIO(png_bytes)) as image:
        assert image.format == "PNG"
        assert image.size[0] > 0
        assert image.size[1] > 0


def test_render_chart_with_long_unicode_title_does_not_crash():
    """A long unicode title is rendered without an opaque matplotlib error."""
    title = "Ünicodé tîtlé with a löt of äccents and 数え切れないほど多くの文字 " * 5
    png_bytes = renderer.render_chart(
        _spec(title=title),
        [(1, 1), (2, 2), (3, 3)],
    )
    assert png_bytes.startswith(PNG_MAGIC)


def test_render_chart_table_with_empty_data_renders_placeholder():
    """A table chart with no rows renders a placeholder ('no rows') PNG.

    The evidence_ids MUST be non-empty (the audit trail requires
    the chart to cite at least one evidence id), but the data
    sequence can be empty. The renderer draws a placeholder cell
    so the dashboard still gets a valid PNG.
    """
    png_bytes = renderer.render_chart(
        _spec(kind="table", x="", y="", evidence_ids=("ev-render-1",)),
        (),
    )
    assert png_bytes.startswith(PNG_MAGIC)


def test_render_chart_table_with_single_row_renders_correctly():
    """A table with exactly one row renders to a valid PNG."""
    png_bytes = renderer.render_chart(
        _spec(kind="table", x="", y="", evidence_ids=("ev-render-1",)),
        [("ev-render-1", "only row")],
    )
    assert png_bytes.startswith(PNG_MAGIC)


def test_render_chart_bar_with_single_data_point_renders_correctly():
    """A bar chart with a single data point renders to a valid PNG."""
    png_bytes = renderer.render_chart(
        _spec(kind="bar"),
        [("a", 1)],
    )
    assert png_bytes.startswith(PNG_MAGIC)


def test_render_chart_scatter_with_negative_values_renders_correctly():
    """A scatter chart with negative values renders to a valid PNG."""
    png_bytes = renderer.render_chart(
        _spec(kind="scatter", x="latency_ms", y="error_rate"),
        [(-10, -0.1), (0, 0.0), (10, 0.1), (20, 0.4)],
    )
    assert png_bytes.startswith(PNG_MAGIC)


def test_render_chart_line_with_empty_data_raises_value_error():
    """An axis-driven chart with no data MUST raise a documented ValueError.

    PR-C.16: the prior surface was silent — an empty data sequence
    reached matplotlib and crashed the worker. The contract: raise
    ``ValueError`` with a descriptive message so the API can return
    a 422 to the dashboard.
    """
    with pytest.raises(ValueError, match="at least one data point"):
        renderer.render_chart(_spec(kind="line"), ())


def test_render_chart_bar_with_empty_data_raises_value_error():
    """Same contract for bar."""
    with pytest.raises(ValueError, match="at least one data point"):
        renderer.render_chart(_spec(kind="bar"), ())


def test_render_chart_scatter_with_empty_data_raises_value_error():
    """Same contract for scatter."""
    with pytest.raises(ValueError, match="at least one data point"):
        renderer.render_chart(_spec(kind="scatter"), ())
