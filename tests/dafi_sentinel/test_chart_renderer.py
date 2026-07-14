"""Tests for the controlled matplotlib chart renderer.

The PR4 renderer must be safe to run inside the dashboard worker:
no GUI backend, no ``plt.show`` side effect, and only PNG bytes
returned to the caller (or a file written under an explicit path).
These tests pin the safety guarantees from the workbench spec.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from dafi_sentinel.charts import renderer
from dafi_sentinel.charts.validation import ChartValidationError
from dafi_sentinel.domain.models import ChartSpec


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


def test_render_chart_to_bytes_returns_valid_png_payload():
    """Rendering must produce a PNG byte stream the dashboard can decode."""
    png_bytes = renderer.render_chart(_spec(), [(1, 10), (2, 20), (3, 15), (4, 25)])

    assert isinstance(png_bytes, bytes)
    assert png_bytes.startswith(PNG_MAGIC)
    # The PNG is a valid image: try to load it with PIL.
    from PIL import Image
    with Image.open(io.BytesIO(png_bytes)) as image:
        assert image.format == "PNG"
        assert image.size[0] > 0
        assert image.size[1] > 0


def test_render_chart_writes_to_path_and_returns_same_bytes():
    """When given a path, the renderer must write the PNG there AND return the bytes."""
    target = Path("/tmp/opencode") / "dafi_pr4_chart.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    png_bytes = renderer.render_chart(_spec(), [(1, 10), (2, 20), (3, 15)], output=target)

    assert target.exists()
    assert target.read_bytes() == png_bytes
    assert png_bytes.startswith(PNG_MAGIC)
    target.unlink()


def test_render_chart_uses_agg_backend_and_does_not_call_plt_show(monkeypatch):
    """The renderer must use the Agg backend and never call ``plt.show``."""
    import matplotlib
    import matplotlib.pyplot as plt

    calls: list[str] = []
    monkeypatch.setattr(plt, "show", lambda *args, **kwargs: calls.append("show"))

    renderer.render_chart(_spec(), [(1, 1), (2, 2)])

    assert calls == [], "plt.show must never be invoked from the controlled renderer"
    assert matplotlib.get_backend().lower() == "agg"


def test_render_chart_raises_validation_error_for_invalid_spec():
    """Defense in depth: the renderer must validate the spec before touching matplotlib."""
    with pytest.raises(ChartValidationError) as failure:
        renderer.render_chart(_spec(title=""), [(1, 1)])
    assert failure.value.field == "title"


@pytest.mark.parametrize(
    "kind, x, y, rows",
    [
        ("line", "timestamp", "errors", [(1, 10), (2, 20), (3, 30)]),
        ("bar", "service", "count", [("a", 1), ("b", 2), ("c", 3)]),
        ("scatter", "latency_ms", "error_rate", [(10, 0.1), (20, 0.2), (30, 0.4)]),
        ("table", "", "", [("ev-render-1", "first row"), ("ev-render-2", "second row")]),
    ],
)
def test_render_chart_supports_each_kind(kind, x, y, rows):
    """Line, bar, scatter, and table must all render to valid PNG bytes."""
    evidence = ("ev-render-1",) if kind != "table" else ("ev-render-1", "ev-render-2")
    spec = _spec(kind=kind, x=x, y=y, evidence_ids=evidence)
    png_bytes = renderer.render_chart(spec, rows)
    assert png_bytes.startswith(PNG_MAGIC)


def test_render_chart_is_deterministic_for_same_input():
    """The renderer must produce byte-identical PNGs for the same spec and data."""
    spec = _spec()
    data = [(1, 10), (2, 20), (3, 30), (4, 25), (5, 35)]
    assert renderer.render_chart(spec, data) == renderer.render_chart(spec, data)
