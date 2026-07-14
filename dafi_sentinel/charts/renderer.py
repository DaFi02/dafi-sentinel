"""Controlled matplotlib chart renderer.

The PR4 renderer is the only place in the codebase that imports
``matplotlib``. It is a server-side, dashboard-renderable PNG emitter
that:

* sets the headless ``Agg`` backend (no GUI, no display);
* never calls ``plt.show``;
* returns the PNG as ``bytes`` so the dashboard can decode it;
* optionally writes the same bytes to a caller-supplied path;
* validates the ``ChartSpec`` before touching matplotlib.

The renderer is intentionally a thin wrapper: a chart is a validated
spec plus a small data sequence, and the output is a PNG. Anything
fancy (annotations, theming, multi-series) belongs to later slices.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from os import PathLike
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

from dafi_sentinel.charts.validation import validate_chart_spec
from dafi_sentinel.domain.models import ChartSpec


# Force the headless backend before any pyplot call. Safe to call
# multiple times; matplotlib resolves the same backend.
matplotlib.use("Agg")


def _draw_axes(ax, spec: ChartSpec, data: Sequence[tuple[object, object]]) -> None:
    xs = [row[0] for row in data]
    ys = [row[1] for row in data]
    if spec.kind == "line":
        ax.plot(xs, ys)
    elif spec.kind == "bar":
        ax.bar(xs, ys)
    elif spec.kind == "scatter":
        ax.scatter(xs, ys)
    else:  # "table" — handled in the dedicated branch, but keep mypy happy.
        raise ValueError(f"unsupported chart kind for axes draw: {spec.kind}")


def _draw_table(fig, spec: ChartSpec, data: Sequence[tuple[object, object]]) -> None:
    ax = fig.add_subplot(111)
    ax.axis("off")
    if not data:
        ax.text(0.0, 1.0, "(no rows)", fontsize=10, verticalalignment="top")
        return
    table = ax.table(cellText=[[str(value) for value in row] for row in data], loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 1.4)


def _build_figure(spec: ChartSpec, data: Sequence[tuple[object, object]]):
    if spec.kind == "table":
        fig = plt.figure(figsize=(6.0, 1.0 + 0.4 * max(len(data), 1)))
        _draw_table(fig, spec, data)
    else:
        fig, ax = plt.subplots(figsize=(6.0, 4.0))
        _draw_axes(ax, spec, data)
        ax.set_xlabel(spec.x)
        ax.set_ylabel(spec.y)
    fig.suptitle(spec.title)
    return fig


def render_chart(
    spec: ChartSpec,
    data: Sequence[tuple[object, object]],
    *,
    output: str | PathLike[str] | None = None,
) -> bytes:
    """Render a chart to PNG bytes.

    Parameters
    ----------
    spec:
        A validated ``ChartSpec``. The renderer re-runs ``validate_chart_spec``
        so callers cannot bypass the safety check.
    data:
        Sequence of ``(x, y)`` tuples for line/bar/scatter, or
        ``(label, value)`` rows for table.
    output:
        Optional filesystem path. When provided, the same PNG bytes are
        also written to this path. The directory must exist.

    Returns
    -------
    bytes
        The PNG payload. The dashboard can decode it directly.

    Raises
    ------
    ChartValidationError
        If the spec fails validation.
    ValueError
        If the data sequence is empty for an axis-driven chart, or if
        the chart kind is unsupported.
    """
    validate_chart_spec(spec)

    if spec.kind not in {"line", "bar", "scatter", "table"}:
        raise ValueError(f"unsupported chart kind: {spec.kind!r}")
    if spec.kind in {"line", "bar", "scatter"} and not data:
        raise ValueError(f"{spec.kind} chart requires at least one data point")

    fig = _build_figure(spec, data)
    try:
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", bbox_inches="tight")
        png_bytes = buffer.getvalue()
    finally:
        plt.close(fig)

    if output is not None:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png_bytes)

    return png_bytes
