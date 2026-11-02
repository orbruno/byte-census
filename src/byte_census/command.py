"""Command scaffold shared by every check.

A check command adds `@format_option`, takes the Click context, and calls
`run_observation` with a function that returns a `CheckResult`. The scaffold
starts the cost meter, stamps `captured_at`, orders the cross-references and
meta arrays, renders JSON or a table, and turns any failure into the typed
error the group prints on stderr. Checks never print and never prompt.
"""

import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import click

from byte_census.cost import CostCounters, CostMeter
from byte_census.errors import to_byte_census_error
from byte_census.model import (
    CoverageEntry,
    Data,
    Envelope,
    Meta,
    Scope,
    UnavailableSource,
    format_captured_at,
    link_references,
    order_coverage,
    order_roots,
    order_suggestions,
    order_unavailable,
)
from byte_census.render import FORMATS, color_enabled, render


@dataclass(frozen=True)
class CheckResult:
    """What a check returns; the scaffold adds meta, cost, and ordering."""

    data: Data
    scope: Scope = field(default_factory=Scope)
    counters: CostCounters = field(default_factory=CostCounters)
    incomplete_coverage: tuple[CoverageEntry, ...] = ()
    unavailable_sources: tuple[UnavailableSource, ...] = ()


Check = Callable[[], CheckResult]


def format_option(func: Callable[..., Any]) -> Callable[..., Any]:
    """`--format json|table`, passed to the command as `output_format`."""
    return click.option(
        "--format",
        "output_format",
        type=click.Choice(FORMATS),
        default="json",
        show_default=True,
        help="Output format: JSON for programs, table for people.",
    )(func)


def _default_now() -> datetime:
    return datetime.now(UTC)


def _use_color() -> bool:
    return color_enabled(sys.stdout, os.environ)


def build_envelope(
    command: str, captured_at: str, result: CheckResult, meter: CostMeter
) -> Envelope:
    """Order the result per the contract and close the cost meter."""
    suggestions = order_suggestions(result.data.suggestions)
    findings, suggestions = link_references(result.data.findings, suggestions)
    scope = replace(
        result.scope,
        roots=order_roots(result.scope.roots),
        skipped_mounts=tuple(sorted(result.scope.skipped_mounts)),
    )
    meta = Meta(
        command=command,
        captured_at=captured_at,
        scope=scope,
        cost=meter.finish(result.counters),
        incomplete_coverage=order_coverage(result.incomplete_coverage),
        unavailable_sources=order_unavailable(result.unavailable_sources),
    )
    data = replace(result.data, findings=findings, suggestions=suggestions)
    return Envelope(data=data, meta=meta)


def run_observation(
    ctx: click.Context,
    command: str,
    output_format: str,
    check: Check,
    *,
    clock: Callable[[], float] | None = None,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Run one check and print its envelope; failures raise ByteCensusError.

    `elapsed_s` runs from the start of this call until the envelope is
    complete, just before serialization. `clock` (monotonic seconds) and
    `now` (aware datetime) default to the system clocks.
    """
    try:
        meter = CostMeter.start(clock or time.monotonic)
        captured_at = format_captured_at((now or _default_now)())
        envelope = build_envelope(command, captured_at, check(), meter)
        text = render(envelope.to_dict(), output_format, color=_use_color())
    except (Exception, KeyboardInterrupt) as error:
        mapped = to_byte_census_error(error)
        raise mapped.with_help(f"{ctx.command_path} --help") from error
    click.echo(text, nl=False)
