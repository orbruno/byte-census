"""Renderers for the envelope: JSON (default) and a human table.

Renderers take the serialized envelope (`Envelope.to_dict()`), so they work
from the contract shape. Color is decided once by `color_enabled`: never when
stdout is not a TTY or `NO_COLOR` is set to a non-empty value.
"""

from collections.abc import Mapping
from typing import Any

from byte_census.render.json_format import render_json
from byte_census.render.table_format import render_table

FORMATS = ("json", "table")


def no_color_requested(environ: Mapping[str, str]) -> bool:
    """NO_COLOR set to a non-empty value (no-color.org)."""
    return bool(environ.get("NO_COLOR"))


def color_enabled(stream: Any, environ: Mapping[str, str]) -> bool:
    """True only for a TTY stream without a non-empty NO_COLOR."""
    if no_color_requested(environ):
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def render(payload: Mapping[str, Any], output_format: str, *, color: bool) -> str:
    """Render the envelope in `output_format`; JSON never carries color."""
    if output_format == "json":
        return render_json(payload)
    if output_format == "table":
        return render_table(payload, color=color)
    raise ValueError(f"unknown output format: {output_format!r}")


__all__ = [
    "FORMATS",
    "color_enabled",
    "no_color_requested",
    "render",
    "render_json",
    "render_table",
]
