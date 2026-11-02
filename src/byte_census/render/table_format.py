"""Table renderer for people (`--format table`).

Byte figures are shown in binary units. Long lists in `meta` are truncated
here only; JSON output is never truncated. ANSI styling is applied only when
the caller passes `color=True`.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

BOLD = "\x1b[1m"
RESET = "\x1b[0m"
UNITS = ("KiB", "MiB", "GiB", "TiB")
COVERAGE_LIMIT = 20
NULL = "-"


def format_bytes(value: int | None) -> str:
    """Binary units with one decimal; `-` for null."""
    if value is None:
        return NULL
    if value < 1024:
        return f"{value} B"
    size = float(value)
    unit = "B"
    for unit in UNITS:
        size /= 1024
        if size < 1024:
            break
    return f"{size:.1f} {unit}"


def _cell(key: str, value: Any) -> str:
    if key.endswith("_bytes") and (value is None or isinstance(value, int)):
        return format_bytes(value)
    if value is None:
        return NULL
    if isinstance(value, (Mapping, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _heading(text: str, color: bool) -> str:
    return f"{BOLD}{text}{RESET}" if color else text


def _grid(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    widths = [
        max(len(line[index]) for line in [header, *rows])
        for index in range(len(header))
    ]
    return [
        "  "
        + "  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip()
        for line in [header, *rows]
    ]


def _title(meta: Mapping[str, Any], color: bool) -> list[str]:
    title = f"byte-census {meta.get('command', '')}"
    line = f"{title}  status: {meta.get('status')}  captured: {meta.get('captured_at')}"
    roots = [root["path"] for root in meta.get("scope", {}).get("roots", [])]
    lines = [_heading(line, color)]
    if roots:
        lines.append("Roots: " + ", ".join(roots))
    return lines


def _summary(summary: Mapping[str, Any], color: bool) -> list[str]:
    rows = [(key, _cell(key, value)) for key, value in summary.items()]
    return ["", _heading("Summary", color), *_grid(("FIELD", "VALUE"), rows)]


def _findings(findings: Sequence[Mapping[str, Any]], color: bool) -> list[str]:
    header = ("KIND", "ALLOCATED", "RECLAIMABLE", "ID", "TARGET")
    rows = [
        (
            item["kind"],
            format_bytes(item.get("allocated_bytes")),
            format_bytes(item.get("reclaimable_estimate_bytes")),
            item["id"],
            item["target"],
        )
        for item in findings
    ]
    title = _heading(f"Findings ({len(findings)})", color)
    return ["", title, *(_grid(header, rows) if rows else ["  none"])]


def _suggestions(suggestions: Sequence[Mapping[str, Any]], color: bool) -> list[str]:
    rows = [(item["risk"], item["id"], item["command"]) for item in suggestions]
    title = _heading(f"Suggestions ({len(suggestions)}), never executed", color)
    return [
        "",
        title,
        *(_grid(("RISK", "ID", "COMMAND"), rows) if rows else ["  none"]),
    ]


def _coverage(entries: Sequence[Mapping[str, Any]], color: bool) -> list[str]:
    if not entries:
        return []
    shown = entries[:COVERAGE_LIMIT]
    rows = [(item["reason"], item["operation"], item["path"]) for item in shown]
    lines = ["", _heading(f"Incomplete coverage ({len(entries)})", color)]
    lines.extend(_grid(("REASON", "OPERATION", "PATH"), rows))
    if len(entries) > COVERAGE_LIMIT:
        lines.append(f"  ... {len(entries) - COVERAGE_LIMIT} more (see JSON output)")
    return lines


def _cost(cost: Mapping[str, Any]) -> list[str]:
    if not cost:
        return []
    parts = [
        f"{cost.get('elapsed_s')} s",
        f"{_cell('n', cost.get('entries_visited'))} entries",
        f"{format_bytes(cost.get('content_bytes_read'))} read",
        f"{_cell('n', cost.get('subprocess_calls'))} subprocess calls",
    ]
    return ["", "Cost: " + ", ".join(parts)]


def render_table(payload: Mapping[str, Any], *, color: bool) -> str:
    """Render a serialized envelope as text tables."""
    data = payload.get("data", {})
    meta = payload.get("meta", {})
    lines = [
        *_title(meta, color),
        *_summary(data.get("summary", {}), color),
        *_findings(data.get("findings", []), color),
        *_suggestions(data.get("suggestions", []), color),
        *_coverage(meta.get("incomplete_coverage", []), color),
        *_cost(meta.get("cost", {})),
    ]
    return "\n".join(lines) + "\n"
